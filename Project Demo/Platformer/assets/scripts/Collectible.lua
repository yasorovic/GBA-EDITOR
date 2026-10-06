
function on_collision_enter(other, my_box, other_box)
    if other_box.tag == "player" then
        global.score = global.score + 1
        interface:get("txt_score"):draw("hud_score")
        self:destroy()
    end

end

function on_collision_exit(other, my_box, other_box)
end
