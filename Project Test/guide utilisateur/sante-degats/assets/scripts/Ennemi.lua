function on_collision_enter(other, my_box, other_box)
    if other.name == "Joueur" and my_box.tag == "tete" and other_box.tag == "pieds" then
        sequence:start("mort")
    end
end

function on_sequence_mort()
    for t = 0, 7 do
        self:squash(t, 8, 30)
        wait(1)
    end
    self:destroy()
end
