-- Fin : generique et retour au debut du jeu.
function on_start()
    interface:get("titre"):draw("fin_titre")
    interface:get("merci"):draw("fin_merci")
    music:jingle("fin")
end

function on_update()
    if input:pressed("start") or input:pressed("a") then
        global.quest = 0
        global.fish = 0
        global.cat = 0
        global.star = 0
        global.entering = 0
        scene:switch("Maison")
    end
end
