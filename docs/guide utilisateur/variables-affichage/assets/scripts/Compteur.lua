function on_start()
    interface:get("Compteur"):draw("hud_compteur")
end

function on_update()
    if input:pressed("a") then
        global.compteur = global.compteur + 1
    end
end
