-- Released + Hover : debout SUR la plaque, relâcher A l'enfonce ou la relève.
function on_interact(who)
    if self.anim == "pressed" then
        self:play_anim("up")
    else
        self:play_anim("pressed")
    end
end
