-- Maison : Maman, l'inventaire et la porte de sortie.
local maman_told = 0

function close_enough(ax, ay)
    local h = actor:get("Hero")
    if math.abs(ax - h.position.x) < 22 and math.abs(ay - h.position.y) < 22 then
        return 1
    end
    return 0
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
    global.talking = 0
    interface:get("DialogBox"):hide()
    layer:get(1):hide()
    layer:get(1).priority = 0
    actor:get("Hero").priority = 1
    actor:get("Maman").priority = 1
    if global.entering == 1 then
        local h = actor:get("Hero")
        h.position = vec2(120, 128)
        global.entering = 0
    end
end

function explore()
    local h = actor:get("Hero")
    if h.position.y > 138 and h.position.x > 100 and h.position.x < 140 then
        sfx:play("sfx_door")
        global.entering = 2
        scene:switch("Village")
        return
    end
    if input:pressed("a") then
        local maman = actor:get("Maman")
        if close_enough(maman.position.x, maman.position.y) == 1 then
            if global.quest == 4 then
                sequence:start("maman_end")
            elseif global.quest == 1 then
                sequence:start("maman_search")
            elseif maman_told == 0 then
                sequence:start("maman_start")
            else
                sequence:start("maman_wait")
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

function on_sequence_maman_start()
    open_box()
    interface:get("Portrait").state = "maman"
    interface:get("Dialogue"):draw("maman_start")
    maman_told = 1
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_maman_wait()
    open_box()
    interface:get("Portrait").state = "maman"
    interface:get("Dialogue"):draw("maman_wait")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_maman_search()
    open_box()
    interface:get("Portrait").state = "maman"
    interface:get("Dialogue"):draw("maman_search")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end

function on_sequence_maman_end()
    open_box()
    interface:get("Portrait").state = "maman"
    interface:get("Dialogue"):draw("maman_end")
    wait(8)
    wait_until(input:pressed("a"))
    close_box()
end
