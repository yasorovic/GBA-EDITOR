-- Écran titre : « PRESS START » scintille, gauche / droite change de langue,
-- START lance la partie.
local lit = -1   -- état affiché de « PRESS START » : 1 visible, 0 caché, -1 pas encore

function on_start()
    music_box:trigger("to_title")
end

function on_update()
    -- Le choix de langue recharge la scène (lang:set), le texte se redessine
    -- donc dans la nouvelle langue (0 = la langue source). Deux langues : gauche et droite se valent.
    if input:pressed("left") or input:pressed("right") then
        if lang:get() == 0 then
            lang:set("jap")
        else
            lang:set("en")
        end
        return
    end

    local want = 0
    if scene.frame % 60 < 36 then
        want = 1
    end
    if want ~= lit then
        lit = want
        local press = interface:get("txt_press_start")
        if want == 1 then
            press:show()
        else
            press:hide()
        end
    end

    if input:pressed("start") then
        scene:switch("SCR_Arena")
    end
end
