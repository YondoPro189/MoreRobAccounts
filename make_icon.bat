@echo off
setlocal
cd /d "%~dp0"

echo === Generando icon.ico desde assets\icon_source.png ===
python -c "from PIL import Image; from pathlib import Path; root=Path('assets'); img=Image.open(root/'icon_source.png').convert('RGBA'); bbox=img.getbbox(); img=img.crop(bbox) if bbox else img; w,h=img.size; side=max(w,h); sq=Image.new('RGBA',(side,side),(0,0,0,0)); sq.paste(img,((side-w)//2,(side-h)//2),img); base=sq.resize((256,256), Image.Resampling.LANCZOS); base.save(root/'icon.png'); base.save(root/'icon.ico', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)]); print('Listo: assets\\icon.ico')"
if errorlevel 1 (
    echo Instala Pillow: pip install pillow
    pause
    exit /b 1
)
echo.
echo Vuelve a compilar con make_release.bat
pause
