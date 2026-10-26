-- Scénario de test du pool partagé : la scène joue ses actions elle-même et écrit PASS ou FAIL dans le log
-- de mGBA (mgba-sdl -l 8 rom.gba, puis fermer la fenêtre pour vider le tampon). Voir README.md.
local boss
local held
local n = 0

function on_update()
    local f = scene.frame

    -- A. Un boss né (racine + deux parties), qui perd un bras tout seul à sa 15e image.
    if f == 5 then
        boss = actor:spawn("Boss", vec2(120, 80))
        if boss ~= nil then
            debug:log("PASS A1 le boss naît")
        else
            debug:log("FAIL A1 le boss naît")
        end
        if actor:count("Boss") == 1 then
            debug:log("PASS A2 un boss")
        else
            debug:log("FAIL A2 un boss")
        end
    end

    -- B. Des balles spawnées pendant que le bras est détruit : elles ne doivent pas prendre sa place.
    if f == 30 then
        for i = 1, 3 do
            actor:spawn("Bullet", vec2(10 * i, 10))
        end
        if actor:count("Bullet") == 3 then
            debug:log("PASS B1 trois balles")
        else
            debug:log("FAIL B1 trois balles")
        end
        if actor:count("Boss") == 1 then
            debug:log("PASS B2 le boss vit toujours")
        else
            debug:log("FAIL B2 le boss vit toujours")
        end
    end

    -- C. Une rafale : 600 spawns d'un coup, le pool refuse ce qu'il ne peut pas tenir.
    if f == 40 then
        for i = 1, 600 do
            actor:spawn("Bullet", vec2(i % 200, 30))
        end
        n = actor:count("Bullet")
        if n == 509 then
            debug:log("PASS C1 pool plein (509 balles)")
        else
            debug:log("FAIL C1 pool plein (509 balles)")
        end
        local extra = actor:spawn("Bullet", vec2(0, 0))
        if extra == nil then
            debug:log("PASS C2 un spawn en trop rend nil")
        else
            debug:log("FAIL C2 un spawn en trop rend nil")
        end
    end
    if f == 60 then
        n = actor:count("Bullet")
        for i = 1, n do
            local b = actor:get("Bullet", 1)
            b:destroy()
        end
        if actor:count("Bullet") == 0 then
            debug:log("PASS C3 toutes détruites")
        else
            debug:log("FAIL C3 toutes détruites")
        end
        if actor:count("Boss") == 1 then
            debug:log("PASS C4 le boss vit toujours")
        else
            debug:log("FAIL C4 le boss vit toujours")
        end
    end

    -- D. Une référence conservée devient nulle quand l'emplacement change de main.
    if f == 70 then
        held = actor:spawn("Bullet", vec2(1, 1))
        if held ~= nil then
            debug:log("PASS D1 référence tenue")
        else
            debug:log("FAIL D1 référence tenue")
        end
    end
    if f == 71 then
        held:destroy()
        local autre = actor:spawn("Bullet", vec2(2, 2))
        if autre ~= nil then
            debug:log("PASS D2 l'emplacement est repris")
        else
            debug:log("FAIL D2 l'emplacement est repris")
        end
    end
    if f == 72 then
        if held == nil then
            debug:log("PASS D3 la référence périmée est nil")
        else
            debug:log("FAIL D3 la référence périmée est nil")
        end
        local autre = actor:get("Bullet", 1)
        autre:destroy()
    end

    -- E. Détruire le boss rend son groupe tout de suite : des balles prennent ses emplacements, puis un
    -- nouveau boss trouve une série libre.
    if f == 80 then
        boss:destroy()
        for i = 1, 3 do
            actor:spawn("Bullet", vec2(10 * i, 50))
        end
        if actor:count("Boss") == 0 then
            debug:log("PASS E1 boss détruit")
        else
            debug:log("FAIL E1 boss détruit")
        end
        if actor:count("Bullet") == 3 then
            debug:log("PASS E2 trois balles dans le groupe rendu")
        else
            debug:log("FAIL E2 trois balles dans le groupe rendu")
        end
    end
    if f == 90 then
        boss = actor:spawn("Boss", vec2(140, 90))
        if boss ~= nil then
            debug:log("PASS E3 un nouveau boss naît")
        else
            debug:log("FAIL E3 un nouveau boss naît")
        end
        if actor:count("Boss") == 1 then
            debug:log("PASS E4 un boss")
        else
            debug:log("FAIL E4 un boss")
        end
    end

    -- F. Un héros né est arrêté par un mur né (le mur à x = 150, le héros part de x = 100).
    if f == 100 then
        actor:spawn("Wall", vec2(150, 120))
        actor:spawn("Hero", vec2(100, 120))
    end
    if f == 180 then
        local h = actor:get("Hero", 1)
        debug:log("hero x = ", h.position.x)
        if h.position.x <= 134 then
            debug:log("PASS F1 le héros est arrêté par le mur")
        else
            debug:log("FAIL F1 le héros est arrêté par le mur")
        end
        if h.position.x > 100 then
            debug:log("PASS F2 le héros a avancé")
        else
            debug:log("FAIL F2 le héros a avancé")
        end
    end

    -- G. Un modèle affine né : 40 spinners, 32 matrices (les 8 derniers sans rotation, avertissement debug).
    if f == 200 then
        for i = 1, 40 do
            actor:spawn("Spinner", vec2(8 * i - 4, 20))
        end
        if actor:count("Spinner") == 40 then
            debug:log("PASS G1 quarante spinners")
        else
            debug:log("FAIL G1 quarante spinners")
        end
    end

    if f == 260 then
        debug:log("FIN")
    end
end
