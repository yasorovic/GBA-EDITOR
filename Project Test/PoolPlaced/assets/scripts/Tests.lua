-- Scénario de test d'un acteur POSÉ dont l'emplacement est repris : Marcheur (prefab Mover) est posé dans la scène,
-- on le détruit, puis un spawn du même prefab reprend son emplacement. Voir README.md.
local x0 = 0
local x1 = 0
local m
local autre

function kill_all()
    local n = actor:count("Mover")
    for i = 1, n do
        local a = actor:get("Mover", 1)
        a:destroy()
    end
end

function on_update()
    local f = scene.frame

    -- A. Le posé vit et avance (son on_update tourne).
    if f == 5 then
        local p = actor:get("Marcheur")
        x0 = p.position.x
        if actor:count("Mover") == 1 then
            debug:log("PASS A1 un Mover posé")
        else
            debug:log("FAIL A1 un Mover posé")
        end
    end
    if f == 25 then
        local p = actor:get("Marcheur")
        if p.position.x >= x0 + 15 then
            debug:log("PASS A2 le posé avance")
        else
            debug:log("FAIL A2 le posé avance")
        end
    end

    -- B. Détruit, il n'existe plus.
    if f == 30 then
        local p = actor:get("Marcheur")
        p:destroy()
        if actor:count("Mover") == 0 then
            debug:log("PASS B1 le posé détruit ne compte plus")
        else
            debug:log("FAIL B1 le posé détruit ne compte plus")
        end
        if actor:get("Marcheur") == nil then
            debug:log("PASS B2 le nom de la scène ne désigne plus rien")
        else
            debug:log("FAIL B2 le nom de la scène ne désigne plus rien")
        end
    end

    -- C. Un spawn du même prefab reprend l'emplacement du posé : le nom de la scène le désigne de nouveau.
    if f == 40 then
        m = actor:spawn("Mover", vec2(100, 40))
        if m ~= nil then
            debug:log("PASS C1 le spawn réussit")
        else
            debug:log("FAIL C1 le spawn réussit")
        end
        if actor:count("Mover") == 1 then
            debug:log("PASS C2 un seul Mover")
        else
            debug:log("FAIL C2 un seul Mover")
        end
        if actor:get("Marcheur") ~= nil then
            debug:log("PASS C3 l'emplacement posé est repris")
        else
            debug:log("FAIL C3 l'emplacement posé est repris")
        end
        x1 = m.position.x
    end
    if f == 60 then
        if m.position.x >= x1 + 15 then
            debug:log("PASS D1 l'instance née dans l'emplacement posé est mise à jour")
        else
            debug:log("FAIL D1 l'instance née dans l'emplacement posé est mise à jour")
        end
    end

    -- E. Une seconde instance naît dans le pool (le posé repris est pris) : les deux cohabitent et avancent.
    if f == 70 then
        autre = actor:spawn("Mover", vec2(10, 80))
        if actor:count("Mover") == 2 then
            debug:log("PASS E1 deux Mover, le posé repris et un du pool")
        else
            debug:log("FAIL E1 deux Mover, le posé repris et un du pool")
        end
        if autre.position.y == 80 and m.position.y == 40 then
            debug:log("PASS E2 deux instances distinctes")
        else
            debug:log("FAIL E2 deux instances distinctes")
        end
    end
    if f == 90 then
        if autre.position.x >= 25 then
            debug:log("PASS E3 l'instance du pool avance")
        else
            debug:log("FAIL E3 l'instance du pool avance")
        end
    end

    -- F. Tout détruire rend les deux emplacements ; trois naissances les reprennent (le posé, puis deux du pool).
    if f == 100 then
        kill_all()
        if actor:count("Mover") == 0 then
            debug:log("PASS F1 tout est détruit")
        else
            debug:log("FAIL F1 tout est détruit")
        end
    end
    if f == 110 then
        for i = 1, 3 do
            actor:spawn("Mover", vec2(20 * i, 120))
        end
        if actor:count("Mover") == 3 then
            debug:log("PASS F2 trois naissances")
        else
            debug:log("FAIL F2 trois naissances")
        end
    end
    if f == 125 then
        if actor:get("Mover", 3) ~= nil and actor:get("Mover", 4) == nil then
            debug:log("PASS F3 trois instances atteignables")
        else
            debug:log("FAIL F3 trois instances atteignables")
        end
        kill_all()
    end

    -- J. La hiérarchie des acteurs POSÉS : Chef > Bras > Pointe (parents de scène). Les enfants se nomment depuis une
    -- référence, parent et root remontent la chaîne, et détruire un maillon ne détruit pas ses enfants.
    if f == 150 then
        local chef = actor:get("Chef")
        local bras = chef.Bras
        local pointe = bras.Pointe
        if bras ~= nil and pointe ~= nil then
            debug:log("PASS J1 chef.Bras et bras.Pointe nomment les enfants posés depuis une référence")
        else
            debug:log("FAIL J1 chef.Bras et bras.Pointe nomment les enfants posés depuis une référence")
        end
        local p = pointe.parent
        if p ~= nil and p.position.x == bras.position.x and p.position.x ~= pointe.position.x then
            debug:log("PASS J2 le parent de Pointe est Bras")
        else
            debug:log("FAIL J2 le parent de Pointe est Bras")
        end
        local r = pointe.root
        if r ~= nil and r.position.x == chef.position.x and r.position.x ~= pointe.position.x then
            debug:log("PASS J3 la racine de Pointe est Chef, deux niveaux plus haut")
        else
            debug:log("FAIL J3 la racine de Pointe est Chef, deux niveaux plus haut")
        end
        if chef.parent == nil then
            debug:log("PASS J4 le sommet n'a pas de parent")
        else
            debug:log("FAIL J4 le sommet n'a pas de parent")
        end
        local rc = chef.root
        if rc ~= nil and rc.position.x == chef.position.x then
            debug:log("PASS J5 la racine du sommet est lui-même")
        else
            debug:log("FAIL J5 la racine du sommet est lui-même")
        end
        chef.Bras:destroy()
    end
    if f == 154 then
        local chef = actor:get("Chef")
        if chef.Bras == nil then
            debug:log("PASS J6 un enfant posé détruit se lit nil")
        else
            debug:log("FAIL J6 un enfant posé détruit se lit nil")
        end
        local pointe = actor:get("Pointe")
        if pointe ~= nil and pointe.parent == nil then
            debug:log("PASS J7 l'enfant d'un maillon détruit survit, sans parent")
        else
            debug:log("FAIL J7 l'enfant d'un maillon détruit survit, sans parent")
        end
        local r = pointe.root
        if r ~= nil and r.position.x == chef.position.x then
            debug:log("PASS J8 sa racine reste le sommet vivant")
        else
            debug:log("FAIL J8 sa racine reste le sommet vivant")
        end
        chef:destroy()
    end
    if f == 158 then
        local pointe = actor:get("Pointe")
        if actor:get("Chef") == nil and pointe ~= nil and pointe.root == nil then
            debug:log("PASS J9 sommet détruit : plus de racine")
        else
            debug:log("FAIL J9 sommet détruit : plus de racine")
        end
    end

    -- L. actor:clear("Mover") détruit l'instance posée reprise ET celles du pool.
    if f == 165 then
        for i = 1, 3 do
            actor:spawn("Mover", vec2(20 * i, 130))
        end
        local n = actor:clear("Mover")
        if n == 3 and actor:count("Mover") == 0 then
            debug:log("PASS L1 clear détruit le posé repris et les instances du pool")
        else
            debug:log("FAIL L1 clear détruit le posé repris et les instances du pool")
        end
    end

    if f == 200 then
        debug:log("FIN")
    end
end
