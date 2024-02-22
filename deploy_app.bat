
mkdir C:\tmp_fld
move %0\..\.dvc C:\tmp_fld
move %0\..\raw_data C:\tmp_fld
move %0\..\venv C:\tmp_fld

rsconnect deploy shiny %0\.. --name ablinston --title UK_House_Prices

move C:\tmp_fld\.dvc %0\..
move C:\tmp_fld\raw_data %0\..
move C:\tmp_fld\venv %0\..
rd /s /q "C:\tmp_fld"