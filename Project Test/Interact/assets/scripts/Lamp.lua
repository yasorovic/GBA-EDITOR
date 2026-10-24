-- Held + Facing : face à la lampe, A tenu une demi-seconde (30 frames) la bascule.
function on_interact(who)
    if self.anim == "on" then
        self:play_anim("off")
    else
        self:play_anim("on")
    end
end
