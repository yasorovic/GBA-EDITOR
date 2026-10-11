-- mgba_frame_probe.lua — à charger dans mGBA (Tools > Scripting… > File > Load script).
--
-- Pour CHAQUE rafraîchissement d'écran, lit le compteur de tours de boucle du
-- moteur (`_g_frame`, celui que le script Lua lit par `scene.frame`) et note
-- combien de tours ont eu lieu depuis le rafraîchissement précédent :
--
--   0 tour    le moteur est encore dans le calcul de l'image d'avant : RALENTI
--   1 tour    nominal : un tour de logique par rafraîchissement
--   2 et plus RATTRAPAGE : le moteur a rejoué plusieurs tours d'affilée
--
-- Toutes les REPORT_EVERY images d'émulateur, une ligne résume la fenêtre.
--
-- ⚠ Écrit d'après l'API de scripting de mGBA 0.10 (callbacks:add, emu:read32,
--   emu:currentFrame, console:log) et NON exécuté au moment de l'écrire : si une
--   fonction manque dans votre version, c'est ici qu'il faut ajuster.

-- Adresse de `_g_frame` dans la ROM chargée. Elle change à chaque build qui
-- modifie le code : la relire avec
--     arm-none-eabi-nm <projet>/build/rom.elf | findstr _g_frame
-- (0x030005F4 est celle de frame_overrun_probe.gba livrée avec ce dossier.)
local G_FRAME_ADDR = 0x030005F4

local REPORT_EVERY = 120   -- images d'émulateur entre deux lignes (2 s à 60 Hz)

local last_tick = nil
local window_start_emu = 0
local window_start_tick = 0
local hist = { [0] = 0, [1] = 0, [2] = 0 }

local function verdict(h)
    if h[2] > 0 then
        return "RATTRAPAGE (plusieurs tours dans un même rafraîchissement)"
    elseif h[0] > 0 then
        return "RALENTI (des rafraîchissements sans nouveau tour de logique)"
    end
    return "nominal"
end

local function on_frame()
    local emu_frame = emu:currentFrame()
    local tick = emu:read32(G_FRAME_ADDR)

    if last_tick ~= nil then
        local delta = tick - last_tick
        if delta < 0 then delta = 0 end   -- compteur remis à zéro (changement de scène)
        if delta > 2 then delta = 2 end
        hist[delta] = hist[delta] + 1
    end
    last_tick = tick

    if emu_frame - window_start_emu >= REPORT_EVERY then
        local span = emu_frame - window_start_emu
        local ticks = tick - window_start_tick
        local per_second = 0
        if ticks > 0 then per_second = (ticks * 60) // span end
        console:log(string.format(
            "image émulateur %d | tour moteur %d | tours/60 images: %d | "
            .. "0 tour: %d  1 tour: %d  2+ tours: %d | %s",
            emu_frame, tick, per_second, hist[0], hist[1], hist[2], verdict(hist)))
        window_start_emu = emu_frame
        window_start_tick = tick
        hist = { [0] = 0, [1] = 0, [2] = 0 }
    end
end

callbacks:add("frame", on_frame)
console:log("mgba_frame_probe: lecture de _g_frame à 0x" .. string.format("%08X", G_FRAME_ADDR))
