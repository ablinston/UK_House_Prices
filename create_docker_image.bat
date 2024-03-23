
mkdir C:\tmp_fld
move %0\..\.dvc C:\tmp_fld
move %0\..\raw_data C:\tmp_fld
move %0\..\venv C:\tmp_fld

cd C:\Users\Andy\Documents\UK_House_Prices

REM Remove the old docker image
docker rmi uk_house_prices

REM Create new docker image
docker build -t uk_house_prices .

move C:\tmp_fld\.dvc %0\..
move C:\tmp_fld\raw_data %0\..
move C:\tmp_fld\venv %0\..
rd /s /q "C:\tmp_fld"