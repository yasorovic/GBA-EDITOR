-- Écran de fin : « VICTORY » ou « DEFEAT », un jingle, puis — une fois le
-- jingle terminé — « PRESS START » scintille et START revient au titre.
local lit = -1   -- état affiché de « PRESS START » : 1 visible, 0 caché, -1 pas encore

function on_start()
    -- La musique de jeu se tait ; le jingle sonne par-dessus le silence.
    music_box:trigger("to_result")
    if global.winner == 0 then
        music:jingle("Claimed DX")
    else
        interface:get("txt_result"):draw("scr_victory_defeat")
        music:jingle("Crystal Clear DX SLOW")
    end
end

function on_update()
    -- Quelques frames de grâce : le jingle doit avoir démarré avant qu'on l'attende.
    if scene.frame < 10 then
        return
    end
    if music:jingle_playing() then
        return
    end

    -- Jingle terminé : « PRESS START » scintille (36 frames visible, 24 caché).
    local want = 0
    if scene.frame % 60 < 36 then
        want = 1
    end
    if want ~= lit then
        lit = want
        local press = interface:get("txt_victory_press_start")
        if want == 1 then
            press:show()
        else
            press:hide()
        end
    end

    if input:pressed("start") then
        scene:switch("SCR_Main")
    end
end
