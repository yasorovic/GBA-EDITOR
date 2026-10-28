function on_collision_enter(other, my_box, other_box) -- check for the player collision
    if other_box.tag == "player" then
        global.score = global.score + 1
        interface:get("txt_score"):draw("hud_score") -- update the score
        self:destroy() -- delete self
    end
end