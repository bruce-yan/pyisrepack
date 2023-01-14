# pyisrepack

### **介绍**
***
将pyc文件重新打入由PyInstaller生成的exe中

### **使用说明**
***
```
Usage: pyi-repack.py -ori <exe file> -p <pyc file> -o <output file>
```

### **修改 PyInstaller 生成的可执行文件中的代码**
*** 
#### pyInstaller 从Exe文件中拆出 pyc 文件
使用py
1. 使用 uncompyle6 将 pyc 文件反编译成 python 源文件
2. 修改python代码
3. 将修改后的python源代码编译成 pyc
4. 使用 pyi-repack.py 将 pyc 重新压入 exe