@ECHO OFF

pushd %~dp0
del /F /Q .\source\*.rst
copy *.rst .\source
"D:\Program Files\Python35\Scripts\sphinx-apidoc.exe" --ext-autodoc -f -o ./source .. ../tests
"D:\Program Files\Python35\Scripts\sphinx-build.exe" -b html ./source ./html

:end
popd

pause
