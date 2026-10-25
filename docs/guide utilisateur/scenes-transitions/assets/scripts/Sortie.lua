function on_collision_enter(other, my_box, other_box)
    if other.name == "Joueur" then
        scene:switch("Victoire")
    end
end
