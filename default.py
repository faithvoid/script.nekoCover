import os
import xbmcgui
import xbmc
import urllib
import urllib2
import struct
import json

# You can force a region ("PAL", "NTSC-U", "NTSC-J") or leave None to auto-detect
OVERRIDE_REGION = None

def find_default_xbe_files(root_dir):
    xbe_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower() == "default.xbe":
                xbe_files.append(os.path.join(dirpath, filename))
    return xbe_files

def read_titleid_and_region(xbe_path):
    try:
        with open(xbe_path, 'rb') as f:
            f.seek(0)
            if f.read(4) != b'XBEH':
                return None, None
            f.seek(0x104)
            base_addr = struct.unpack('<I', f.read(4))[0]
            f.seek(0x118)
            cert_addr = struct.unpack('<I', f.read(4))[0]
            cert_offset = cert_addr - base_addr

            # Title ID
            f.seek(cert_offset + 0x8)
            titleid = struct.unpack('<I', f.read(4))[0]

            # Region - Untested! There may be dragons.
            f.seek(cert_offset + 0xC)
            region_mask = struct.unpack('<I', f.read(4))[0]
            region_names = []
            if region_mask & 0x01:
                region_names.append("NTSC-U")
            if region_mask & 0x02:
                region_names.append("NTSC-J")
            if region_mask & 0x04:
                region_names.append("PAL")
            preferred_region = OVERRIDE_REGION or (region_names[0] if region_names else None)

            return "%08X" % titleid, preferred_region

    except Exception as e:
        xbmc.log("XBE Read Error: {}".format(str(e)), level=xbmc.LOGERROR)
        return None, None

def download_thumbnail_from_api(title_id, save_path, preferred_region=None):
    try:
        url = "https://mobcat.zip/XboxIDs/api.php?id={}&imgs".format(title_id)
        response = urllib2.urlopen(url, timeout=10)
        data = json.load(response)

        if not isinstance(data, list) or len(data) == 0:
            return False

        def region_priority(entry):
            region = entry.get("Region", "")
            if preferred_region and preferred_region in region:
                return 0
            return 1

        sorted_data = sorted(data, key=region_priority)

        for entry in sorted_data:
            imgs = entry.get("imgs")
            if not imgs or not isinstance(imgs, dict):
                continue

            for region_key in imgs:
                region_data = imgs[region_key]
                if not isinstance(region_data, dict):
                    continue

                thumb_url = region_data.get("Thumbnail")
                if not thumb_url:
                    continue

                tmp_path = save_path + ".tmp"

                try:
                    urllib.urlretrieve(thumb_url, tmp_path)
                    with open(tmp_path, "rb") as f:
                        content = f.read()

                    if b"404" in content:
                        os.remove(tmp_path)
                        xbmc.log("Invalid or missing thumbnail for TitleID {} at {}".format(title_id, thumb_url), level=xbmc.LOGWARNING)
                        continue

                    if os.path.exists(save_path):
                        os.remove(save_path)
                    os.rename(tmp_path, save_path)
                    return True

                except Exception as e:
                    xbmc.log("Download error for {}: {}".format(thumb_url, str(e)), level=xbmc.LOGERROR)
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

        return False

    except Exception as e:
        xbmc.log("API Error for {}: {}".format(title_id, str(e)), level=xbmc.LOGERROR)
        return False

def main():
    dialog = xbmcgui.Dialog()
    root_dir = dialog.browse(0, "Select Game Root Folder", "files")

    if not root_dir:
        dialog.ok("nekoCover", "No folder selected.")
        return

    xbe_files = find_default_xbe_files(root_dir)

    if not xbe_files:
        dialog.ok("nekoCover", "No default.xbe files found.")
        return

    total = len(xbe_files)
    count = 0

    progress = xbmcgui.DialogProgress()
    progress.create("nekoCover", "Scanning games...")

    for index, xbe_path in enumerate(xbe_files):
        if progress.iscanceled():
            break

        folder_name = os.path.basename(os.path.dirname(xbe_path))
        title_id, region = read_titleid_and_region(xbe_path)

        if title_id:
            tbn_path = os.path.join(os.path.dirname(xbe_path), "default.tbn")
            if download_thumbnail_from_api(title_id, tbn_path, preferred_region=region):
                count += 1

        percent = int((float(index + 1) / total) * 100)
        progress.update(percent, "Processing: {}".format(folder_name), "Downloaded: {}".format(count), "Remaining: {}".format(total - (index + 1)))

    progress.close()
    dialog.ok("nekoCover", "Done!", "Thumbnails downloaded: {}".format(count))

if __name__ == "__main__":
    main()
