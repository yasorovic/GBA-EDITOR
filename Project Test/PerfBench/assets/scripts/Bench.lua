-- Banc de mesure du coût CPU des fonctions et des patrons de l'API Lua (voir README.md).
-- La scène joue des phases de 70 images, l'une après l'autre. Chaque phase écrit une ligne
-- "PHASE <nom> <n>" dans le log de mGBA (n = nombre d'instances ou d'appels par image), puis le runtime écrit
-- "frame us=..." à chaque image. tools/run_perf_bench.py range les durées par phase.
local phase = 0
local t = 0
local acc = 0

function on_update()
    t = t + 1

    -- Début de phase : on pose les acteurs de la mesure.
    if t == 1 then
        if phase == 0 then
            debug:log("PHASE vide ", 0)
        end
        if phase == 1 then
            debug:log("PHASE balles_immobiles ", 100)
            for i = 1, 100 do
                actor:spawn("Bullet", vec2(i * 2, 30))
            end
        end
        if phase == 2 then
            debug:log("PHASE spinners_affines ", 30)
            for i = 1, 30 do
                actor:spawn("Spinner", vec2(i * 6, 60))
            end
        end
        if phase == 3 then
            debug:log("PHASE poursuite_directe ", 1)
            actor:spawn("Hero", vec2(120, 100))
            actor:spawn("ChaseDirect", vec2(10, 20))
        end
        if phase == 4 then
            debug:log("PHASE poursuite_directe ", 50)
            actor:spawn("Hero", vec2(120, 100))
            for i = 1, 50 do
                actor:spawn("ChaseDirect", vec2(i * 4, 20 + i % 50))
            end
        end
        if phase == 5 then
            debug:log("PHASE poursuite_en_cache ", 50)
            actor:spawn("Hero", vec2(120, 100))
            for i = 1, 50 do
                actor:spawn("ChaseCached", vec2(i * 4, 20 + i % 50))
            end
        end
        if phase == 6 then
            debug:log("PHASE poursuite_un_quart ", 50)
            actor:spawn("Hero", vec2(120, 100))
            for i = 1, 50 do
                actor:spawn("ChaseThrottled", vec2(i * 4, 20 + i % 50))
            end
        end
        if phase == 7 then
            debug:log("PHASE poursuite_manuelle ", 50)
            actor:spawn("Hero", vec2(120, 100))
            for i = 1, 50 do
                actor:spawn("ChaseManual", vec2(i * 4, 20 + i % 50))
            end
        end
        if phase == 8 then
            debug:log("PHASE parcours_get_i ", 100)
            for i = 1, 100 do
                actor:spawn("Bullet", vec2(i * 2, 30))
            end
        end
        if phase == 9 then
            debug:log("PHASE spawn_destroy ", 10)
        end
        if phase == 10 then
            debug:log("PHASE count ", 100)
            for i = 1, 10 do
                actor:spawn("Bullet", vec2(i * 2, 30))
            end
        end
        if phase == 11 then
            debug:log("PHASE fin ", 0)
        end
    end

    -- Travail de la phase, à chaque image.
    if phase == 8 then
        for i = 1, actor:count("Bullet") do
            local b = actor:get("Bullet", i)
            acc = acc + b.position.x
        end
    end
    if phase == 9 then
        for i = 1, 10 do
            local b = actor:spawn("Bullet", vec2(i * 2, 30))
            if b then
                b:destroy()
            end
        end
    end
    if phase == 10 then
        for i = 1, 100 do
            acc = acc + actor:count("Bullet")
        end
    end

    -- Fin de phase : on rend tous les emplacements.
    if t == 70 and phase < 11 then
        actor:clear("Bullet")
        actor:clear("Spinner")
        actor:clear("Hero")
        actor:clear("ChaseDirect")
        actor:clear("ChaseCached")
        actor:clear("ChaseThrottled")
        actor:clear("ChaseManual")
        phase = phase + 1
        t = 0
    end
    if t == 150 and phase == 11 then
        debug:log("FIN")
    end
end
