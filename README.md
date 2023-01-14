# pyisrepack

### **Introduce**
***
将pyc文件重新打入由PyInstaller生成的exe中.<br>
本项目基于 [pyinstxtractor](https://github.com/extremecoders-re/pyinstxtractor)

### **Usage**
***
```
Usage: python pyisrepack.py -ori <exe file> -p <pyc file> -o <output file>
```

### **How To Do**
*** 
这是Demo代码, 使用 PyInstaller 将其打包为 main.exe
```python
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel


def main():
    app = QApplication(sys.argv)
    label = QLabel("Hello world.", alignment=Qt.AlignmentFlag.AlignCenter)
    label.resize(300, 200)
    label.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```
运行效果如下

![pic1](https://gitee.com/bruce_code/pyisrepack/blob/master/docimgs/1.png)

我们将通过以下步骤将 Hello world 改为 Hello earth
#### Step1. 使用 [pyinstxtractor](https://github.com/extremecoders-re/pyinstxtractor) 将 exe 拆包
```
python pyinstxtractor.py main.exe
```
得到如下文件

![pic2](https://gitee.com/bruce_code/pyisrepack/blob/master/docimgs/2.png)

其中main.pyc是我们要修改的文件

#### Step2. 使用 [uncompyle6](https://github.com/rocky/python-uncompyle6) 将 pyc 文件反编译成 python 源文件
```
uncompyle6 -o . main.pyc
```

#### Step3. 修改python代码
```
label = QLabel("Hello earth.", alignment=Qt.AlignmentFlag.AlignCenter)
```

#### Step4. 将修改后的python源代码编译成 pyc
```
uncompyle6 -c main.py
```

#### Step5. 使用 pyisrepack.py 将 pyc 重新压入 exe
```
Usage: python pyisrepack.py -ori main.exe -p main.pyc -o new_main.exe
```

#### Step6. 运行效果
![pic3](https://gitee.com/bruce_code/pyisrepack/blob/master/docimgs/3.png)

### **Important**
***
* 修改前后应尽量保证 Python 版本一致
* 目前只支持exe中 类型为 "s" 的条目。

### 使用 pyi-archive_viewer 查看条目类型
***
```
 pos, length, uncompressed, iscompressed, type, name
[(0, 225, 293, 1, 'm', 'struct'),
 (225, 1025, 1706, 1, 'm', 'pyimod01_os_path'),
 (1250, 4025, 8765, 1, 'm', 'pyimod02_archive'),
 (5275, 7386, 17758, 1, 'm', 'pyimod03_importers'),
 (12661, 1456, 3638, 1, 'm', 'pyimod04_ctypes'),
 (14117, 824, 1364, 1, 's', 'pyiboot01_bootstrap'),
 (14941, 512, 797, 1, 's', 'pyi_rth_subprocess'),
 (15453, 701, 1065, 1, 's', 'pyi_rth_pkgutil'),
 (16154, 439, 660, 1, 's', 'pyi_rth_inspect'),
 (16593, 330, 441, 1, 's', 'pyi_rth_pyside6'),
 (16923, 381, 529, 1, 's', 'main'),
 (17304, 1173690, 1173690, 0, 'z', 'PYZ-00.pyz')]
```

### See Also
***
* https://github.com/extremecoders-re/pyinstxtractor
* https://github.com/rocky/python-uncompyle6

### License
***
GNU General Public License v3.0