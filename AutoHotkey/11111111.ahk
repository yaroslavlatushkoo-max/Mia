; Путь к исполняемому файлу Lively (версия из Microsoft Store)
lively_path := "C:\Program Files\Lively Wallpaper\Lively.exe"

; --- ПУТИ К ВАШИМ ДВУМ ОБОЯМ (скопируйте из папки Library) ---
path_to_wallpaper_1 := "A:\Обои\91562-629172467_medium.mp4"
path_to_wallpaper_2 := "A:\Обои\205733-927672950_medium.mp4"
; -------------------------------------------------

; Горячая клавиша: Win + 1
Numpad6::
    Run, "%lively_path%" setwp --file "%path_to_wallpaper_1%" --monitor 1,, Hide
return

; Горячая клавиша: Win + 2
Numpad3::
    Run, "%lively_path%" setwp --file "%path_to_wallpaper_2%" --monitor 1,, Hide
return