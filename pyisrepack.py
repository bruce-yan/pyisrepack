from __future__ import print_function
import os
import struct
import marshal
import zlib
import sys
from uuid import uuid4 as uniquename
import argparse
import copy


class CTOCEntry:
    def __init__(self, position, cmprsdDataSize, uncmprsdDataSize, cmprsFlag, typeCmprsData, name):
        self.position = position
        self.cmprsdDataSize = cmprsdDataSize
        self.uncmprsdDataSize = uncmprsdDataSize
        self.cmprsFlag = cmprsFlag
        self.typeCmprsData = typeCmprsData
        self.name = name


class PyInstArchive:
    PYINST20_COOKIE_SIZE = 24           # For pyinstaller 2.0
    PYINST21_COOKIE_SIZE = 24 + 64      # For pyinstaller 2.1+
    MAGIC = b'MEI\014\013\012\013\016'  # Magic number which identifies pyinstaller

    def __init__(self, path):
        self.filePath = path
        self.pycMagic = b'\0' * 4
        self.barePycList = [] # List of pyc's whose headers have to be fixed


    def open(self):
        try:
            self.fPtr = open(self.filePath, 'rb')
            self.fileSize = os.stat(self.filePath).st_size
        except:
            print('[!] Error: Could not open {0}'.format(self.filePath))
            return False
        return True


    def close(self):
        try:
            self.fPtr.close()
        except:
            pass


    def checkFile(self):
        print('[+] Processing {0}'.format(self.filePath))

        searchChunkSize = 8192
        endPos = self.fileSize
        self.cookiePos = -1

        if endPos < len(self.MAGIC):
            print('[!] Error : File is too short or truncated')
            return False

        while True:
            startPos = endPos - searchChunkSize if endPos >= searchChunkSize else 0
            chunkSize = endPos - startPos

            if chunkSize < len(self.MAGIC):
                break

            self.fPtr.seek(startPos, os.SEEK_SET)
            data = self.fPtr.read(chunkSize)

            offs = data.rfind(self.MAGIC)

            if offs != -1:
                self.cookiePos = startPos + offs
                break

            endPos = startPos + len(self.MAGIC) - 1

            if startPos == 0:
                break

        if self.cookiePos == -1:
            print('[!] Error : Missing cookie, unsupported pyinstaller version or not a pyinstaller archive')
            return False

        self.fPtr.seek(self.cookiePos + self.PYINST20_COOKIE_SIZE, os.SEEK_SET)

        if b'python' in self.fPtr.read(64).lower():
            print('[+] Pyinstaller version: 2.1+')
            self.pyinstVer = 21     # pyinstaller 2.1+
        else:
            self.pyinstVer = 20     # pyinstaller 2.0
            print('[+] Pyinstaller version: 2.0')

        return True


    def getCArchiveInfo(self):
        try:
            if self.pyinstVer == 20:
                self.fPtr.seek(self.cookiePos, os.SEEK_SET)

                # Read CArchive cookie
                (magic, lengthofPackage, toc, tocLen, pyver) = \
                struct.unpack('!8siiii', self.fPtr.read(self.PYINST20_COOKIE_SIZE))

            elif self.pyinstVer == 21:
                self.fPtr.seek(self.cookiePos, os.SEEK_SET)

                # Read CArchive cookie
                (magic, lengthofPackage, toc, tocLen, pyver, pylibname) = \
                struct.unpack('!8sIIii64s', self.fPtr.read(self.PYINST21_COOKIE_SIZE))

        except:
            print('[!] Error : The file is not a pyinstaller archive')
            return False

        self.pymaj, self.pymin = (pyver//100, pyver%100) if pyver >= 100 else (pyver//10, pyver%10)
        print('[+] Python version: {0}.{1}'.format(self.pymaj, self.pymin))

        # Additional data after the cookie
        tailBytes = self.fileSize - self.cookiePos - (self.PYINST20_COOKIE_SIZE if self.pyinstVer == 20 else self.PYINST21_COOKIE_SIZE)

        # Overlay is the data appended at the end of the PE
        self.overlaySize = lengthofPackage + tailBytes
        self.overlayPos = self.fileSize - self.overlaySize
        self.tableOfContentsPos = self.overlayPos + toc
        self.tableOfContentsSize = tocLen

        print('[+] Length of package: {0} bytes'.format(lengthofPackage))
        return True


    def parseTOC(self):
        # Go to the table of contents
        self.fPtr.seek(self.tableOfContentsPos, os.SEEK_SET)

        self.tocList = []
        parsedLen = 0

        # Parse table of contents
        while parsedLen < self.tableOfContentsSize:
            (entrySize, ) = struct.unpack('!i', self.fPtr.read(4))
            nameLen = struct.calcsize('!iIIIBc')

            (entryPos, cmprsdDataSize, uncmprsdDataSize, cmprsFlag, typeCmprsData, name) = \
            struct.unpack( \
                '!IIIBc{0}s'.format(entrySize - nameLen), \
                self.fPtr.read(entrySize - 4))

            name = name.decode('utf-8').rstrip('\0')
            if len(name) == 0:
                name = str(uniquename())
                print('[!] Warning: Found an unamed file in CArchive. Using random name {0}'.format(name))

            self.tocList.append( \
                                CTOCEntry(                      \
                                    self.overlayPos + entryPos, \
                                    cmprsdDataSize,             \
                                    uncmprsdDataSize,           \
                                    cmprsFlag,                  \
                                    typeCmprsData,              \
                                    name                        \
                                ))

            parsedLen += entrySize
        print('[+] Found {0} files in CArchive'.format(len(self.tocList)))


    def _writeRawData(self, filepath, data):
        nm = filepath.replace('\\', os.path.sep).replace('/', os.path.sep).replace('..', '__')
        nmDir = os.path.dirname(nm)
        if nmDir != '' and not os.path.exists(nmDir): # Check if path exists, create if not
            os.makedirs(nmDir)

        with open(nm, 'wb') as f:
            f.write(data)


    def extractFiles(self):
        print('[+] Beginning extraction...please standby')
        extractionDir = os.path.join(os.getcwd(), os.path.basename(self.filePath) + '_extracted')

        if not os.path.exists(extractionDir):
            os.mkdir(extractionDir)

        os.chdir(extractionDir)

        for entry in self.tocList:
            self.fPtr.seek(entry.position, os.SEEK_SET)
            data = self.fPtr.read(entry.cmprsdDataSize)

            if entry.cmprsFlag == 1:
                data = zlib.decompress(data)
                # Malware may tamper with the uncompressed size
                # Comment out the assertion in such a case
                assert len(data) == entry.uncmprsdDataSize # Sanity Check

            if entry.typeCmprsData == b'd' or entry.typeCmprsData == b'o':
                # d -> ARCHIVE_ITEM_DEPENDENCY
                # o -> ARCHIVE_ITEM_RUNTIME_OPTION
                # These are runtime options, not files
                continue

            basePath = os.path.dirname(entry.name)
            if basePath != '':
                # Check if path exists, create if not
                if not os.path.exists(basePath):
                    os.makedirs(basePath)

            if entry.typeCmprsData == b's':
                # s -> ARCHIVE_ITEM_PYSOURCE
                # Entry point are expected to be python scripts
                print('[+] Possible entry point: {0}.pyc'.format(entry.name))

                if self.pycMagic == b'\0' * 4:
                    # if we don't have the pyc header yet, fix them in a later pass
                    self.barePycList.append(entry.name + '.pyc')
                self._writePyc(entry.name + '.pyc', data)

            elif entry.typeCmprsData == b'M' or entry.typeCmprsData == b'm':
                # M -> ARCHIVE_ITEM_PYPACKAGE
                # m -> ARCHIVE_ITEM_PYMODULE
                # packages and modules are pyc files with their header intact

                # From PyInstaller 5.3 and above pyc headers are no longer stored
                # https://github.com/pyinstaller/pyinstaller/commit/a97fdf
                if data[2:4] == b'\r\n':
                    # < pyinstaller 5.3
                    if self.pycMagic == b'\0' * 4: 
                        self.pycMagic = data[0:4]
                    self._writeRawData(entry.name + '.pyc', data)

                else:
                    # >= pyinstaller 5.3
                    if self.pycMagic == b'\0' * 4:
                        # if we don't have the pyc header yet, fix them in a later pass
                        self.barePycList.append(entry.name + '.pyc')

                    self._writePyc(entry.name + '.pyc', data)

            else:
                self._writeRawData(entry.name, data)

                if entry.typeCmprsData == b'z' or entry.typeCmprsData == b'Z':
                    self._extractPyz(entry.name)

        # Fix bare pyc's if any
        self._fixBarePycs()


    def _fixBarePycs(self):
        for pycFile in self.barePycList:
            with open(pycFile, 'r+b') as pycFile:
                # Overwrite the first four bytes
                pycFile.write(self.pycMagic)


    def _writePyc(self, filename, data):
        with open(filename, 'wb') as pycFile:
            pycFile.write(self.pycMagic)            # pyc magic

            if self.pymaj >= 3 and self.pymin >= 7:                # PEP 552 -- Deterministic pycs
                pycFile.write(b'\0' * 4)        # Bitfield
                pycFile.write(b'\0' * 8)        # (Timestamp + size) || hash 

            else:
                pycFile.write(b'\0' * 4)      # Timestamp
                if self.pymaj >= 3 and self.pymin >= 3:
                    pycFile.write(b'\0' * 4)  # Size parameter added in Python 3.3

            pycFile.write(data)


    def _extractPyz(self, name):
        dirName =  name + '_extracted'
        # Create a directory for the contents of the pyz
        if not os.path.exists(dirName):
            os.mkdir(dirName)

        with open(name, 'rb') as f:
            pyzMagic = f.read(4)
            assert pyzMagic == b'PYZ\0' # Sanity Check

            pyzPycMagic = f.read(4) # Python magic value

            if self.pycMagic == b'\0' * 4:
                self.pycMagic = pyzPycMagic

            elif self.pycMagic != pyzPycMagic:
                self.pycMagic = pyzPycMagic
                print('[!] Warning: pyc magic of files inside PYZ archive are different from those in CArchive')

            # Skip PYZ extraction if not running under the same python version
            if self.pymaj != sys.version_info.major or self.pymin != sys.version_info.minor:
                print('[!] Warning: This script is running in a different Python version than the one used to build the executable.')
                print('[!] Please run this script in Python {0}.{1} to prevent extraction errors during unmarshalling'.format(self.pymaj, self.pymin))
                print('[!] Skipping pyz extraction')
                return

            (tocPosition, ) = struct.unpack('!i', f.read(4))
            f.seek(tocPosition, os.SEEK_SET)

            try:
                toc = marshal.load(f)
            except:
                print('[!] Unmarshalling FAILED. Cannot extract {0}. Extracting remaining files.'.format(name))
                return

            print('[+] Found {0} files in PYZ archive'.format(len(toc)))

            # From pyinstaller 3.1+ toc is a list of tuples
            if type(toc) == list:
                toc = dict(toc)

            for key in toc.keys():
                (ispkg, pos, length) = toc[key]
                f.seek(pos, os.SEEK_SET)
                fileName = key

                try:
                    # for Python > 3.3 some keys are bytes object some are str object
                    fileName = fileName.decode('utf-8')
                except:
                    pass

                # Prevent writing outside dirName
                fileName = fileName.replace('..', '__').replace('.', os.path.sep)

                if ispkg == 1:
                    filePath = os.path.join(dirName, fileName, '__init__.pyc')

                else:
                    filePath = os.path.join(dirName, fileName + '.pyc')

                fileDir = os.path.dirname(filePath)
                if not os.path.exists(fileDir):
                    os.makedirs(fileDir)

                try:
                    data = f.read(length)
                    data = zlib.decompress(data)
                except:
                    print('[!] Error: Failed to decompress {0}, probably encrypted. Extracting as is.'.format(filePath))
                    open(filePath + '.encrypted', 'wb').write(data)
                else:
                    self._writePyc(filePath, data)


    def _readPyc(self, filename):
        with open(filename, 'rb') as pycFile:
            pycFile.seek(4, os.SEEK_SET)
            if self.pymaj >= 3 and self.pymin >= 7:                # PEP 552 -- Deterministic pycs
                pycFile.seek(8, os.SEEK_CUR)
            else:
                pycFile.seek(4, os.SEEK_CUR)
                if self.pymaj >= 3 and self.pymin >= 3:
                    pycFile.seek(4, os.SEEK_CUR)

            data = pycFile.read()
        return data

    
    def replacePyc(self, pycFile, outputFile):
        _, fileName = os.path.split(pycFile)
        fileName,_ = os.path.splitext(fileName)

        findEntry = None
        newTocList = copy.deepcopy(self.tocList)

        for index in range(len(self.tocList)):
            _, fname = os.path.split(self.tocList[index].name)
            if fileName == fname:
                setattr(self.tocList[index], "replaceFlag", 1)
                break

        for index in range(len(newTocList)):
            _, fname = os.path.split(newTocList[index].name)
            if fileName == fname:
                findEntry = newTocList[index]
                setattr(findEntry, "replaceFlag", 1)
                break
        
        if not findEntry:
            print("{} entry not found.".format(fileName))
            return

        if findEntry.typeCmprsData != b's':
            print("Only support 's' entry type. use pyi-archive_viewer to lookat types".format(fileName))
            return

        oldPos = findEntry.position
    
        data = self._readPyc(pycFile)
        uncmprsdDataSize = len(data)
        data = zlib.compress(data)
        size = len(data)

        contentOffset = size - findEntry.cmprsdDataSize
        findEntry.cmprsdDataSize = size
        findEntry.uncmprsdDataSize = uncmprsdDataSize
    
        for index in range(len(newTocList)):
            if newTocList[index].position > oldPos:
                newTocList[index].position += contentOffset

        self._saveToOutput(outputFile, newTocList, data)

    
    def _saveNewToc(self, f, newTocList):
        lenght = 0
        for entry in newTocList:
            entry.name = entry.name.encode("utf-8")
            formatStr = "!iIIIBc{}s".format(len(entry.name) + 1)
            entrySize = struct.calcsize(formatStr)
            lenght += entrySize
            d = struct.pack(formatStr, entrySize, entry.position - self.overlayPos, entry.cmprsdDataSize, entry.uncmprsdDataSize, entry.cmprsFlag, entry.typeCmprsData, entry.name)
            f.write(d)
        return lenght
        
    
    def _saveToOutput(self, outputFile, newTocList, data):
        with open(outputFile, "wb") as f:
            # 1. 写入loader
            self.fPtr.seek(0, os.SEEK_SET)
            loader = self.fPtr.read(self.overlayPos)
            f.write(loader)
            # 2. 写入文件内容
            newLengthofPackage = 0
            for entry in self.tocList:
                if hasattr(entry, "replaceFlag") and entry.replaceFlag == 1:
                    f.write(data)
                    newLengthofPackage += len(data)
                else:
                    self.fPtr.seek(entry.position)
                    d = self.fPtr.read(entry.cmprsdDataSize)
                    f.write(d)
                    newLengthofPackage += entry.cmprsdDataSize
            # 3. 写入toc
            newTocPos = newLengthofPackage
            newTocLen = self._saveNewToc(f, newTocList)

            bodyLen = newLengthofPackage + newTocLen
            # 4. 写入文件尾
            if self.pyinstVer == 20:
                self.fPtr.seek(self.cookiePos, os.SEEK_SET)

                tailLen = struct.calcsize('!8siiii')
                bodyLen += tailLen

                # Read CArchive cookie
                (magic, lengthofPackage, toc, tocLen, pyver) = \
                struct.unpack('!8siiii', self.fPtr.read(self.PYINST20_COOKIE_SIZE))
                
                tailData = struct.pack('!8siiii', magic, bodyLen, newTocPos, newTocLen, pyver)

            elif self.pyinstVer == 21:
                self.fPtr.seek(self.cookiePos, os.SEEK_SET)

                tailLen = struct.calcsize('!8sIIii64s')
                bodyLen += tailLen

                # Read CArchive cookie
                (magic, lengthofPackage, toc, tocLen, pyver, pylibname) = \
                struct.unpack('!8sIIii64s', self.fPtr.read(self.PYINST21_COOKIE_SIZE))
                
                tailData = struct.pack('!8sIIii64s', magic, bodyLen, newTocPos, newTocLen, pyver, pylibname)

            f.write(tailData)
            f.flush()


def paramToOpt():
    parser = argparse.ArgumentParser()
    parser.add_argument('-ori', "--originalfile", default=None, type=str, help='original exe')
    parser.add_argument('-p', "--pyc", default=None, type=str, help='pyc file')
    parser.add_argument('-o', "--output", default=None, type=str, help='output file')
    opt = parser.parse_args()
    return opt


def main():
    opt = paramToOpt()
    if not opt.originalfile or not opt.pyc:
        print('[+] Usage: pyinsrepack.py -ori <original exe> -p <pyc file> -o <output file>')
        return
    arch = PyInstArchive(opt.originalfile)
    if not arch.open():
        return
    if not arch.checkFile():
        arch.close()
        return
    if not arch.getCArchiveInfo():
        arch.close()
        return
    arch.parseTOC()
    if not arch.replacePyc(opt.pyc, opt.output):
        arch.close()
        return
    arch.close()

if __name__ == '__main__':
    main()