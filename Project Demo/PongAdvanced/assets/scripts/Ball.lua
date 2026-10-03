-- La balle : physique, rebonds, décompte des points, effets et musique.
-- Les scores DESCENDENT : chaque camp part de 10, marquer retire un point au
-- compteur de celui qui marque, et le premier à zéro gagne.

local speed = 512        -- vitesse horizontale, Q8 (512 = 2 px/frame)
local serve_dir = 1      -- sens du service : 1 = vers la droite, -1 = vers la gauche
local serve_timer = 45   -- frames d'attente avant le service

-- Effet visuel en cours. pop, squash et stretch écrivent tous sprite_scale : un
-- seul peut jouer à la fois, d'où un compteur unique et le genre en cours.
-- FX_NONE rend la main à l'étirement continu lié à la vitesse.
local FX_NONE    = 0   -- rien en cours : l'étirement suit juste la vitesse
local FX_POP     = 1   -- apparition : la balle grossit depuis rien
local FX_SQUASH  = 2   -- mur haut/bas : elle s'aplatit dans le sens du choc
local FX_STRETCH = 3   -- raquette : le choc vient du côté, elle s'allonge
local fx = 1
local fx_t = 0

-- Niveau de la musique (1 lente, 2 normale, 3 rapide) : elle accélère avec la balle.
local music_level = 1

-- Replace la balle au centre, immobile ; on_update la relance à la fin de l'attente.
function place_ball(direction)
    serve_dir = direction
    serve_timer = 45
    speed = 512
    fx = FX_POP
    fx_t = 0
    self.position = vec2(116, 76)
    self.velocity = vec2(0, 0)
    self.rotation = 0

    -- Nouvelle manche : la musique revient à son tempo de départ.
    if music_level > 1 then
        music_box:trigger("slow_down")
        music_level = 1
    end
end

-- Fait avancer l'effet en cours ; sans effet, la balle s'étire avec sa vitesse
-- et s'oriente dans le sens de son déplacement.
function play_fx()
    if fx ~= FX_NONE then
        fx_t = fx_t + 1
        if fx == FX_POP then
            self:pop(fx_t, 14, 40)
            if fx_t >= 14 then fx = FX_NONE end
        elseif fx == FX_SQUASH then
            self:squash(fx_t, 9, 35)
            if fx_t >= 9 then fx = FX_NONE end
        elseif fx == FX_STRETCH then
            self:stretch(fx_t, 10, 45)
            if fx_t >= 10 then fx = FX_NONE end
        end
    else
        local vel = self.velocity
        -- vel est en Q8 : /256 ramène en px/frame avant le carré. La vitesse est
        -- mesurée ×100 (×10000 sous la racine : math.sqrt est entier).
        local vx = vel.x / 256
        local vy = vel.y / 256
        local speed100 = math.sqrt((vx * vx + vy * vy) * 10000)
        local stretch = math.clamp(100 + (speed100 - 200) / 2, 100, 140)
        self.sprite_scale = vec2(stretch, 200 - stretch)
    end
end

function on_start()
    if math.rand(0, 1) == 0 then
        place_ball(-1)
    else
        place_ball(1)
    end
end

function on_update()
    if serve_timer > 0 then
        serve_timer = serve_timer - 1
        play_fx()
        if serve_timer == 0 then
            self.velocity = vec2(speed * serve_dir, math.rand(-2, 2) * 64)
        end
        return
    end

    self:apply_velocity()
    local pos = self.position
    local vel = self.velocity

    -- Rebond sur le haut et le bas de l'écran
    if pos.y < 0 then
        self.position = vec2(pos.x, 0)
        self.velocity = vec2(vel.x, math.abs(vel.y))
        sfx:play("WALLBOUNCE")
        fx = FX_SQUASH
        fx_t = 0
    end
    if pos.y > 152 then
        self.position = vec2(pos.x, 152)
        self.velocity = vec2(vel.x, -math.abs(vel.y))
        sfx:play("WALLBOUNCE")
        fx = FX_SQUASH
        fx_t = 0
    end

    -- Sortie à gauche : le joueur a laissé passer, l'adversaire marque
    if pos.x < -8 then
        global.score_cpu = global.score_cpu - 1
        if global.score_cpu <= 0 then
            global.winner = 1
            scene:switch("SCR_Victory")
            return
        end
        sfx:play("GoalTaken")
        place_ball(-1)
        return
    end

    -- Sortie à droite : l'adversaire a laissé passer, le joueur marque
    if pos.x > 240 then
        global.score_player = global.score_player - 1
        if global.score_player <= 0 then
            global.winner = 0
            scene:switch("SCR_Victory")
            return
        end
        sfx:play("GOAL")
        place_ball(1)
        return
    end

    -- L'orientation suit la vélocité : l'axe que squash/stretch étirent tourne avec elle.
    local v = self.velocity
    self.rotation = math.atan2(v.y, v.x)
    play_fx()
end

-- Contact avec une raquette : la balle repart de l'autre côté, plus vite, avec
-- un angle qui dépend du point d'impact (centre = tir droit, bords = en biais).
function on_collision_enter(other, my_box, other_box)
    local offset = (self.position.y + 4) - (other.position.y + 16)
    local vy = math.clamp(offset * 85, -512, 512)

    speed = math.min(speed + 32, 1024)
    sfx:play("PADDLEBOUNCE")

    -- Le choc arrive par le côté : la balle s'écrase en largeur, donc s'allonge en hauteur.
    fx = FX_STRETCH
    fx_t = 0

    if self.position.x < 120 then
        self.velocity = vec2(speed, vy)
    else
        self.velocity = vec2(-speed, vy)
    end

    -- La musique monte d'un cran à 4 échanges (speed 640), puis à 10 (speed 832).
    if music_level == 1 and speed >= 640 then
        music_box:trigger("speed_up")
        music_level = 2
    end
    if music_level == 2 and speed >= 832 then
        music_box:trigger("speed_up")
        music_level = 3
    end
end
