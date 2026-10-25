local rencontre = 0

function on_collision_enter(other, my_box, other_box)
    if other.name ~= "Joueur" then
        return
    end

    if rencontre == 0 then
        interface:get("Dialogue"):draw("villageois_bonjour")
        rencontre = 1
    else
        interface:get("Dialogue"):draw("villageois_apres_bonjour")
    end
end
