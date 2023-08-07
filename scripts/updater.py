#! /usr/bin/env python3

import atexit
import fileinput
import os
import requests
import shutil
import tempfile

from launchpadlib.launchpad import Launchpad
from PySquashfsImage import SquashFsImage
from shutil import copyfile

snap = os.getenv('SNAP')
snapdata = os.getenv('SNAP_DATA')
snapcommon = os.getenv('SNAP_COMMON')

cachedir = snapdata+"/.launchpadlib/cache/"
launchpad = Launchpad.login_anonymously('just testing', 'production', cachedir, version='devel')
tmpdir = tempfile.mkdtemp()
outdir = snapcommon+"/out"

print("created "+tmpdir)

def cleanup(tmpdir):
    print("removing "+tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)

atexit.register(cleanup, tmpdir)

def get_download_url(core, arch):
    apiurl = "https://api.snapcraft.io/v2/snaps/info/"
    url = apiurl+core+"?architecture="+arch+"&fields=revision,download"
    headers = {'Snap-Device-Series': '16'}
    resp = requests.get(url=url, headers=headers).json()

    #print('getting download url for '+core+' '+arch)
    for channel in resp['channel-map']:
        if channel['channel']['name'] == "stable":
            return str(channel['revision'])+" "+channel['download']['url']

def download_snap(core, rev, url):
    outfile = tmpdir+'/'+core+'_'+rev+'.snap'
    snap = requests.get(url)

    print('downloading '+outfile)
    with open(outfile, 'wb') as f:
        f.write(snap.content)
    return outfile

def extract_dpkg_list(core, arch, rev, squashfs):
    image = SquashFsImage.from_file(squashfs)
    outfile = tmpdir+'/'+core+'-'+arch+'-'+rev+'-dpkg.list'

    
    dpkgFile = image.find("dpkg.list")
    if dpkgFile is not None:
         with open(outfile,'wb') as f:
            f.write(dpkgFile.read_bytes())
            print(outfile+' saved')
            return outfile
    image.close()
    if os.path.isfile(squashfs):
        os.remove(squashfs)

def get_src_for_deb(distro, arch, bin_deb, bin_ver):
    ubuntu = launchpad.distributions["ubuntu"]
    archive = ubuntu.main_archive
    url = ""

    # We are still using console-conf and subiquitycore from focal in the jammy.
    if (bin_deb == "console-conf" or bin_deb == "subiquitycore") and distro == "jammy":
        distro = "focal"

    # for some reason, the dpkg file in the latest core22 snap shows 0.0.20 although 
    # launchpad has 0.0.20build5 
    if (bin_deb == "probert-common" or bin_deb == "probert-network") and distro == "jammy":
        bin_ver="0.0.20build5"
    
    if (bin_deb == "cryptsetup" or bin_deb == "cryptsetup-bin" or bin_deb == "libcryptsetup12" ) and distro == "jammy":
        bin_ver = bin_ver.split('+')[0]

    if (bin_deb == "libplymouth5" or bin_deb == "plymouth" or bin_deb == "plymouth-label-ft" ) and distro == "jammy":
        bin_deb = "plymouth"
        bin_ver = bin_ver.rsplit("~", 1)[0].rsplit(".", 1)[0]

    series = "https://api.launchpad.net/1.0/ubuntu/"+distro+"/"+arch

    try:
      mysrc=archive.getPublishedBinaries(exact_match=True, binary_name=bin_deb, version=bin_ver, distro_arch_series=series)[0]
      url = "https://launchpad.net/ubuntu/+source/"+mysrc.source_package_name+"/"+mysrc.source_package_version
    except:
      try:
        owner = launchpad.people["snappy-dev"]
        archive = owner.getPPAByName(name="image")
        mysrc = archive.getPublishedBinaries(exact_match=True, binary_name=bin_deb, version=bin_ver, distro_arch_series=series)[0]
        url = "https://launchpad.net/~snappy-dev/+archive/ubuntu/image/+packages?field.name_filter="+mysrc.source_package_name+"&field.status_filter=published&field.series_filter="+distro
      except:
        owner = launchpad.people["canonical-foundations"]
        archive = owner.getPPAByName(name="ubuntu-image")
        mysrc = archive.getPublishedBinaries(exact_match=True, binary_name=bin_deb, version=bin_ver, distro_arch_series=series)[0]
        url = "https://launchpad.net/~canonical-foundations/+archive/ubuntu/ubuntu-image/+packages?field.name_filter="+mysrc.source_package_name+"&field.status_filter=published&field.series_filter="+distro

    srcdata = url+" "+mysrc.source_package_name+" "+mysrc.source_package_version
    return srcdata

def parse_dpkg_list(dpkg_list, arch):
    with open(dpkg_list) as f:
        lines = [line.rstrip() for line in f]

    basename = os.path.basename(dpkg_list)
    corever = basename.split('-')[0]
    dists = {"core": "xenial", "core18": "bionic", "core20": "focal", "core22": "jammy"}
    distro = dists[corever]

    tabledata = []

    for line in lines:
        if line.startswith("ii"):
            parsedline = line.split()
            package = parsedline[1].split(':')[0]
            version = parsedline[2]
            # ignore special cased fake packages (core20 seeds a fake avahi-daemon)
            # https://github.com/snapcore/core20/commit/d2163f62de8ffc9664a07b008107055a8cd35d06
            if distro == "focal" and package == "avahi-daemon":
                continue
            link, src_name, src_version = get_src_for_deb(distro, arch, package, version).split()
            tabledata.append(gen_table_row(package, version, link, src_name, src_version))
    return tabledata

def gen_table_row(binary, binary_version, link, src_name, src_version):
    icon = "http://cdimage.ubuntu.com/cdicons/jigdo.png"
    prefix="   <tr><td valign=top><img src="+icon+" alt=[   ] width=22 height=22></td><td>"
    td = "</td><td align=right>"
    link = "<a href="+link+">"+src_name+"</a>"
    suffix = "</td></tr>"
    return prefix+binary+td+binary_version+td+link+td+src_version+suffix

def gen_html_head(coretype, arch, rev, outfile):
    infile = snap+"/templates/header.html"

    copyfile(infile, outfile)

    srchtxt = "CORETYPE ARCHITECTURE REVISION".split()
    repltxt = {"CORETYPE": coretype, "ARCHITECTURE": arch, "REVISION": rev}

    for searchitem in srchtxt:
        with fileinput.FileInput(outfile, inplace=True, backup='.bak') as file:
            for line in file:
                print(line.replace(str(searchitem), repltxt[searchitem]), end='')

def gen_html_page(coretype, arch, rev, dpkg_list):
    outfile = tmpdir+"/tmp.html"

    gen_html_head(coretype, arch, rev, outfile)

    content = parse_dpkg_list(dpkg_list, arch)

    with open(outfile, "a") as file_object:
        for line in content:
            file_object.write(str(line)+'\n')
        file_object.write('\n  </table>\n </div>\n</body>\n</html>')

def gen_index(outdir, coretype):
    icon = "http://cdimage.ubuntu.com/cdicons/list.png"
    prefix = "   <tr><td valign=top><img src="+icon+" alt=[   ] width=22 height=22></td><td>"
    td = "</td><td align=right>"
    suffix = "</td></tr>"
    release = coretype.capitalize()

    fin = open(snap+'/templates/index-header.html', 'rt')
    fout = open(outdir+'/'+coretype+'/index.html', 'wt')

    for line in fin:
        fout.write(line.replace('DISTRO', release))

    for link in os.listdir(outdir+'/'+coretype):
        if link.endswith('.html') and '-' in link:
            arch = link.split('-')[0]
            ver = link.split('-')[1].strip('.html')
            data = prefix+release+td+ver+td+arch+td
            data = data+"<a href="+link+">Packagelist</a> <a href="+arch
            data = data+"-"+ver+"-dpkg.list>(Raw Data)</a>"+suffix+"\n"
            fout.write(data)
    fout.write("  </table>\n </div>\n</body>\n</html>")

    fin.close()
    fout.close()

cores = ['core18', 'core20', 'core22']
arches = ['amd64', 'arm64', 'armhf']

for coretype in cores:
    for arch in arches:
        rev, url = get_download_url(coretype, arch).split()
        corename = arch+"-"+rev
        outfile = outdir+"/"+coretype+"/"+corename+".html"
        outlist = outdir+"/"+coretype+"/"+corename+"-dpkg.list"

        if not os.path.isfile(outfile):
            print ("Processing new snap "+coretype+" "+rev+" ("+arch+")")
            coresnap = download_snap(coretype, rev, url)
            dpkg_list = extract_dpkg_list(coretype, arch, rev, coresnap)

            gen_html_page(coretype, arch, rev, dpkg_list)

            copyfile(tmpdir+"/tmp.html", outfile)
            copyfile(tmpdir+"/"+coretype+"-"+corename+"-dpkg.list", outlist)

    gen_index(outdir, coretype)

shutil.rmtree(tmpdir, ignore_errors=True)
