-- Scène de jeu : remet les deux compteurs à 10 et les affiche.
-- Les scores descendent : le premier à zéro gagne (voir Ball.lua).
local shown_player = -1
local shown_cpu = -1

local playerscoring = interface:get("PlayerScoring")     
local cpuscoring =  interface:get("cpuScoring")

function on_start()
    --music_box:trigger("to_arena")
    global.score_player = 10
    global.score_cpu = 10
end

-- On ne redessine que lorsqu'un score change : le texte est effacé d'abord, pour
-- qu'un « 10 » devenu « 9 » ne laisse pas son « 0 » derrière lui.
function on_late_update()
    if global.score_player ~= shown_player then
        shown_player = global.score_player
        playerscoring:clear()
        playerscoring:draw("$score_player")
    end
    if global.score_cpu ~= shown_cpu then
        shown_cpu = global.score_cpu
        cpuscoring:clear()
        cpuscoring:draw("$score_cpu")
    end
end
