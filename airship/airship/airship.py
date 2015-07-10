from __future__ import division
import re
import zlib
import io

import icloud
import steamcloud

try:
    import PIL.Image
    imagemanip = True
    print('airship: PIL.Image successfully imported')
except ImportError as e:
    imagemanip = False
    print('airship: PIL.Image failed to import; {0}'.format(e))

# Data manipulation functions

# Identity

def identity_read(filename, timestamp, data, origin):
    return ([(filename, timestamp, data)], {})

def identity_compare(filename, data1, data2):
    return data1 == data2

def identity_write(filename, data, destination, meta):
    return (filename, data)

def noop_after(filedata, modules, metadata):
    pass

# The Banner Saga

def bannersaga_transform_argb_rgb(orig):
    result = bytearray()
    orig = orig[13:]
    for i in range(len(orig) // 4):
        byteindex = i * 4
        result += orig[byteindex + 1:byteindex + 4]
    return bytes(result)

def bannersaga_transform_rgb_argb(orig):
    result = bytearray(b'\x00\x00\x01\xe0\x00\x00\x01h\x00\x00\x00\x00\x00')
    for i in range(len(orig) // 3):
        byteindex = i * 3
        result += b'\xFF' + orig[byteindex:byteindex + 3]
    return bytes(result)

def bannersaga_read(filename, timestamp, data, origin):
    if imagemanip:
        if origin == 'steamcloud' and filename.endswith('png'):
            filename = filename[:-3] + 'img'
            data = PIL.Image.open(io.BytesIO(data))
        if origin == 'icloud' and filename.endswith('bmpzip'):
            filename = filename[:-6] + 'img'
            data = PIL.Image.frombytes('RGB', (480, 360), bannersaga_transform_argb_rgb(zlib.decompress(bytes(data))))
        return ([(filename, timestamp, data)], {})
    else:
        return ([] if (filename.endswith('png') or filename.endswith('bmpzip')) else [(filename, timestamp, data)], {})

def bannersaga_compare(filename, data1, data2):
    if filename.endswith('img'):
        return data1.histogram() == data2.histogram()
    return data1 == data2

def bannersaga_write(filename, data, destination, meta):
    if filename.endswith('img'):
        if destination == 'steamcloud':
            filename = filename[:-3] + 'png'
            pngbytes = io.BytesIO()
            data.save(pngbytes, 'png', optimize=True)
            data = pngbytes.getvalue()
        if destination == 'icloud':
            filename = filename[:-3] + 'bmpzip'
            data = zlib.compress(bannersaga_transform_rgb_argb(data.tobytes()), 9)
    return (filename, data)

# Transistor

def transistor_read(filename, timestamp, data, origin):
    filename = filename[0].lower() + filename[1:]
    return ([(filename, timestamp, data)], {})

def transistor_write(filename, data, destination, meta):
    if destination == 'icloud':
        filename = filename[0].upper() + filename[1:]
    return (filename, data)

# Costume Quest

costumequest_timeplayedregex = re.compile(b'^.+(;TimePlayed=([1-9]*[0-9](\.[0-9]+)?)).*$')

def costumequest_read(filename, timestamp, data, origin):
    meta = {}
    if origin == 'icloud':
        match = costumequest_timeplayedregex.match(data).groups()
        meta[filename] = match[1]
        data = data[:4] + b'\x0b' + data[5:].replace(b'_mobile', b'').replace(match[0], b'')
    return ([(filename, timestamp, data)], meta)

def costumequest_write(filename, data, destination, meta):
    if destination == 'icloud':
        semicolonafterplacementsindex = data.find(b';', data.find(b'DestroyedPlacements'))
        if semicolonafterplacementsindex == -1:
            semicolonafterplacementsindex = len(data)
        data = data[:4] + b'\x0c' + data[5:semicolonafterplacementsindex] + b';TimePlayed=' + (b'0' if not filename in meta else meta[filename]) + data[semicolonafterplacementsindex:]
        lastworldsindex = 0
        while True:
            lastworldsindex = data.find(b'worlds/', lastworldsindex)
            if lastworldsindex != -1:
                lastworldsindex = lastworldsindex + 7
                slashindex = data.find(b'/', lastworldsindex)
                dotindex = data.find(b'.', lastworldsindex)
                data = data[:slashindex] + b'_mobile' + data[slashindex:dotindex] + b'_mobile' + data[dotindex:]
            else:
                break
    return (filename, data)

# gameobj()

def gameobj(obj):
    if not 'read' in obj:
        obj['read'] = identity_read
    if not 'compare' in obj:
        obj['compare'] = identity_compare
    if not 'write' in obj:
        obj['write'] = identity_write
    if not 'after' in obj:
        obj['after'] = noop_after
    return obj

# Main synchronization function

def sync():
    games = [gameobj({
        'name': 'The Banner Saga',
        'regex': re.compile(r'^[0-4]/(resume|sav_(chapter[1235]|(leaving)?(einartoft|frostvellr)|(dengl|dund|hridvaldy|radormy|skog)r|bjorulf|boersgard|finale|grofheim|hadeborg|ingrid|marek|ridgehorn|sigrholm|stravhs|wyrmtoe))\.(bmpzip|png|save\.json)$'),
        'folder': 'save/saga1',
        'steamcloudid': '237990',
        'icloudid': 'MQ92743Y4D~com~stoicstudio~BannerSaga',
        'read': bannersaga_read,
        'compare': bannersaga_compare,
        'write': bannersaga_write
    }), gameobj({
        'name': 'Transistor',
        'regex': re.compile(r'^[Pp]rofile[1-5]\.sav$'),
        'steamcloudid': '237930',
        'icloudid': 'GPYC69L4CR~iCloud~com~supergiantgames~transistor',
        'icloudfolder': 'Documents',
        'read': transistor_read,
        'write': transistor_write
    }), gameobj({
        'name': 'Costume Quest',
        'regex': re.compile(r'^CQ(_DLC)?_save_[012]$'),
        'steamcloudid': '115100',
        'icloudid': '8VM2L59D89~com~doublefine~cqios',
        'icloudfolder': 'Documents',
        'read': costumequest_read,
        'write': costumequest_write
    })]

    modules = [steamcloud, icloud]
    workingmodules = {}
    modulenum = 0

    for module in modules:
        if module.init():
            print('airship: airship.{0}.init() returned True, using it'.format(module.name))
            workingmodules[module.name] = module
            modulenum += 1
        else:
            print('airship: airship.{0}.init() returned False, not using it'.format(module.name))

    if modulenum > 1:

        for game in games:
            gamemodules = []
            metadata = {}
            cancontinue = True

            print('airship: Trying to sync {0}'.format(game['name']))

            for module in modules:
                if module.name + 'id' in game:
                    if not module.name in workingmodules:
                        print('airship: Module airship.{0} is not available; not syncing this game'.format(module.name))
                        cancontinue = False
                        break
                    else:
                        print('airship: Module airship.{0} is available'.format(module.name))
                        module = workingmodules[module.name]

                        if module.name + 'folder' in game or 'folder' in game:
                            module.set_folder(game['folder'] if not module.name + 'folder' in game else game[module.name + 'folder'])

                        module.set_id(game[module.name + 'id'])

                        if module.will_work():
                            print('airship: Module airship.{0}.will_work() returned True, using it'.format(module.name))
                            gamemodules.append(module)
                        else:
                            print('airship: Module airship.{0}.will_work() returned False; not syncing this game'.format(module.name))
                            module.shutdown()
                            cancontinue = False
                            break

            if cancontinue:
                filetimestamps = {}
                filedata = {}
                files = {}
                for moduleindex in range(len(gamemodules)):
                    cancontinue = False
                    for filename in gamemodules[moduleindex].get_file_names():
                        if game['regex'].match(filename):
                            readobject = game['read'](filename, gamemodules[moduleindex].get_file_timestamp(filename), gamemodules[moduleindex].read_file(filename), gamemodules[moduleindex].name)
                            metadata.update(readobject[1])
                            for itemfilename, itemfiletimestamp, itemfiledata in readobject[0]:
                                if not itemfilename in filetimestamps:
                                    filetimestamps[itemfilename] = [-1] * len(gamemodules)
                                filetimestamps[itemfilename][moduleindex] = itemfiletimestamp
                                if not itemfilename in filedata:
                                    filedata[itemfilename] = [-1] * len(gamemodules)
                                filedata[itemfilename][moduleindex] = itemfiledata
                            cancontinue = True
                if cancontinue:
                    print('airship: Syncing {0}'.format(game['name']))
                    for filename in filetimestamps:
                        for timestamp in filetimestamps[filename]:
                            if timestamp == 0:
                                print('airship: At least one timestamp for file {0} is 0; not syncing this file'.format(filename))
                                cancontinue = False
                                break
                        if cancontinue:
                            newerfilesmayexist = True
                            highestlowtimestamp = -1
                            if cancontinue:
                                while newerfilesmayexist:
                                    newerfilesmayexist = False
                                    lowesttimestamp = 2000000000
                                    lowesttimestampindex = -1
                                    for moduleindex in range(len(gamemodules)):
                                        if highestlowtimestamp < filetimestamps[filename][moduleindex] < lowesttimestamp and filetimestamps[filename][moduleindex] > 0:
                                            lowesttimestamp = filetimestamps[filename][moduleindex]
                                            lowesttimestampindex = moduleindex
                                    if lowesttimestampindex != -1:
                                        newerfilesmayexist = True
                                        highestlowtimestamp = lowesttimestamp
                                        for moduleindex in range(len(gamemodules)):
                                            if moduleindex != lowesttimestampindex and filetimestamps[filename][moduleindex] > 0 and game['compare'](filename, filedata[filename][lowesttimestampindex], filedata[filename][moduleindex]):
                                                filetimestamps[filename][moduleindex] = lowesttimestamp

                                highesttimestamp = -1
                                highesttimestampindex = -1
                                for moduleindex in range(len(gamemodules)):
                                    if filetimestamps[filename][moduleindex] > highesttimestamp:
                                        highesttimestamp = filetimestamps[filename][moduleindex]
                                        highesttimestampindex = moduleindex
                                files[filename] = filedata[filename][highesttimestampindex]
                                for moduleindex in range(len(gamemodules)):
                                    if moduleindex != highesttimestampindex and filetimestamps[filename][moduleindex] < highesttimestamp:
                                        writeobject = game['write'](filename, files[filename], gamemodules[moduleindex].name, metadata)
                                        gamemodules[moduleindex].write_file(writeobject[0], writeobject[1])
                    game['after'](files, modules, metadata)
                else:
                    print('airship: Module airship.{0}.get_file_names() didn\'t return any matched files; not syncing this game'.format(gamemodules[moduleindex].name))

            print('airship: Completed syncing {0}; shutting down modules'.format(game['name']))
            for module in gamemodules:
                module.shutdown()
    else:
        print('airship: Can\'t sync anything (fewer than 2 modules)')
