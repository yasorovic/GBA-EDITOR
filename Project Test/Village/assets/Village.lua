-- Village : dialogues, quete du chat, inventaire et portes.
local lila_hinted = 0

function close_enough(ax, ay)
    local h = actor:get("Hero")
    if math.abs(ax - h.position.x) < 22 and math.abs(ay - h.position.y) < 22 then
        return 1
    end
    return 0
end

function refresh_hud()
    local s1 = interface:get("slot1")
    local s2 = interface:get("slot2")
    local s3 = interface:get("slot3")
    s1:show()
    s2:show()
    s3:show()
    if global.fish == 1 then
        s1.state = "poisson"
    else
        s1.state = "vide"
    end
    if global.cat == 1 then
        s2.state = "chat"
    else
        s2.state = "vide"
    end
    if global.star == 1 then
        s3.state = "etoile"
    else
        s3.state = "vide"
    end
end

-- Le cadre nine-slice est écrit en tuiles dans BG1 : hide() du conteneur ne l'enlève pas, on cache le calque.
function open_box()
    layer:get(1):show()
    global.talking = 1
    interface:get("DialogBox"):show()
    interface:get("Portrait"):show()
end

function close_box()
    interface:get("Dialogue"):clear()
    interface:get("DialogBox"):hide()
    layer:get(1):hide()
    global.talking = 0
end

function on_start()
    layer:get(0):show()
    global.talking = 0
    interface:get("DialogBox"):hide()
    layer:get(1):hide()
    refresh_hud()
    layer:get(1).priority = 0
    local h = actor:get("Hero")
    h.priority = 1
    actor:get("Mamie").priority = 1
    actor:get("Gaston").priority = 1
    actor:get("Lila").priority = 1
    if global.cat == 0 then
        actor:get("Minou").priority = 1
    end
    if global.entering == 2 then
        h.position = vec2(200, 84)
        global.entering = 0
    end
    if global.cat == 1 then
        actor:get("Minou"):destroy()
    end
    if global.quest == 4 then
        local m = actor:get("Minou")
        m.position = vec2(84, 80)
    end
end

function explore()
    local h = actor:get("Hero")
    if input:pressed("up") and h.position.x > 188 and h.position.x < 212 and h.position.y < 92 and h.position.y > 64 then
        sfx:play("sfx_door")
        global.entering = 1
        scene:switch("Maison")
        return
    end
    if input:pressed("a") then
        local mamie = actor:get("Mamie")
        local gaston = actor:get("Gaston")
        local lila = actor:get("Lila")
        local minou = actor:get("Minou")
        if close_enough(mamie.position.x, mamie.position.y) == 1 then
            if global.quest == 4 then
                sequence:start("mamie_after")
            elseif global.cat == 1 then
                sequence:start("mamie_thanks")
            elseif global.quest == 0 then
                sequence:start("mamie_ask")
            else
                sequence:start("mamie_wait")
            end
        elseif close_enough(gaston.position.x, gaston.position.y) == 1 then
            if global.quest == 4 then
                sequence:start("gaston_end")
            elseif global.quest == 0 then
                sequence:start("gaston_early")
            elseif global.fish == 0 and global.cat == 0 then
                sequence:start("gaston_fish")
            else
                sequence:start("gaston_wait")
            end
        elseif close_enough(lila.position.x, lila.position.y) == 1 then
            if global.quest == 4 then
                sequence:start("lila_end")
            elseif global.quest == 0 then
                sequence:start("lila_early")
            elseif lila_hinted == 0 then
                sequence:start("lila_hint")
            else
                sequence:start("lila_wait")
            end
        elseif minou ~= nil and close_enough(minou.position.x, minou.position.y) == 1 then
            if global.fish == 1 then
                sequence:start("minou_caught")
            else
                sequence:start("minou_wary")
            end
        end
    end
end

-- Pas de "return" ici : il sauterait aussi l'avancement des sequences.
function on_update()
    if global.talking == 0 then
        explore()
    end
end

-- Mamie Odile ---------------------------------------------------------------
function on_sequence_mamie_ask()
    open_box()
    interface:get("Portrait").state = "mamie"
    interface:get("Dialogue"):draw("mamie_ask_1")
    wait(8)
    wait_until(input:pressed("a"))
    interface:get("Dialogue"):draw("mamie_ask_2")
    global.quest = 1
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_mamie_wait()
    open_box()
    interface:get("Portrait").state = "mamie"
    interface:get("Dialogue"):draw("mamie_wait")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_mamie_after()
    open_box()
    interface:get("Portrait").state = "mamie"
    interface:get("Dialogue"):draw("mamie_after")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_mamie_thanks()
    open_box()
    interface:get("Portrait").state = "mamie"
    interface:get("Dialogue"):draw("mamie_thanks_1")
    wait(8)
    wait_until(input:pressed("a"))
    interface:get("Dialogue"):draw("mamie_thanks_2")
    sfx:play("sfx_quest")
    global.cat = 0
    global.star = 1
    global.quest = 4
    refresh_hud()
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
    wait(40)
    scene:switch("Fin")
end

-- Gaston le boulanger ---------------------------------------------------------
function on_sequence_gaston_early()
    open_box()
    interface:get("Portrait").state = "gaston"
    interface:get("Dialogue"):draw("gaston_early")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_gaston_fish()
    open_box()
    interface:get("Portrait").state = "gaston"
    interface:get("Dialogue"):draw("gaston_fish_1")
    wait(8)
    wait_until(input:pressed("a"))
    interface:get("Dialogue"):draw("gaston_fish_2")
    sfx:play("sfx_item")
    global.fish = 1
    refresh_hud()
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_gaston_wait()
    open_box()
    interface:get("Portrait").state = "gaston"
    interface:get("Dialogue"):draw("gaston_wait")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_gaston_end()
    open_box()
    interface:get("Portrait").state = "gaston"
    interface:get("Dialogue"):draw("gaston_end")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

-- Lila ------------------------------------------------------------------------
function on_sequence_lila_early()
    open_box()
    interface:get("Portrait").state = "lila"
    interface:get("Dialogue"):draw("lila_early")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_lila_hint()
    open_box()
    interface:get("Portrait").state = "lila"
    interface:get("Dialogue"):draw("lila_hint_1")
    wait(8)
    wait_until(input:pressed("a"))
    interface:get("Dialogue"):draw("lila_hint_2")
    lila_hinted = 1
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_lila_wait()
    open_box()
    interface:get("Portrait").state = "lila"
    interface:get("Dialogue"):draw("lila_wait")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_lila_end()
    open_box()
    interface:get("Portrait").state = "lila"
    interface:get("Dialogue"):draw("lila_end")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

-- Minou le chat ---------------------------------------------------------------
function on_sequence_minou_wary()
    open_box()
    interface:get("Portrait"):hide()
    sfx:play("sfx_meow")
    interface:get("Dialogue"):draw("minou_wary")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_minou_caught()
    open_box()
    interface:get("Portrait"):hide()
    sfx:play("sfx_meow")
    interface:get("Dialogue"):draw("minou_caught_1")
    wait(8)
    wait_until(input:pressed("a"))
    global.fish = 0
    global.cat = 1
    actor:get("Minou"):destroy()
    refresh_hud()
    sfx:play("sfx_item")
    interface:get("Dialogue"):draw("minou_caught_2")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end
