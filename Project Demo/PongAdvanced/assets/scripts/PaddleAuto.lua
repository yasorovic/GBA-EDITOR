-- IA de la raquette adverse. Trois comportements :
--   1. Quand la balle arrive, elle PRÉDIT où elle croisera sa ligne (rebonds sur
--      le haut et le bas compris) au lieu de la suivre des yeux.
--   2. Elle met un instant à réagir, vise un point d'impact aléatoire sur sa
--      raquette (donc un angle de renvoi varié), et rate une balle sur huit.
--   3. Quand la balle s'éloigne, elle revient vers le centre en se balançant
--      doucement, au lieu de rester figée.
-- Elle va à la même vitesse maximale que le joueur (2 px/frame) et ralentit en
-- approchant de sa cible : le mouvement est fluide, pas saccadé.
-- Course du haut de la balle entre les murs haut et bas de la carte de collision
-- (mur haut = tuiles jusqu'à y = 16, mur bas = tuiles à partir de y = 144, balle de 8 px).
-- À recaler si les murs sont repeints.
local BALL_MIN_Y = 16
local BALL_SPAN = 120   -- 144 - 8 - BALL_MIN_Y
local target = 56
local was_incoming = false
local react = 0          -- frames de réaction restantes avant de bouger
local hit_t = 99         -- frames depuis le dernier choc (effets stretch/wobble, cf. PaddlePlayer.lua)

function on_update()
    local ball = actor:get("BALL")
    local incoming = false
    if ball ~= nil then
        if ball.velocity.x > 0 then
            incoming = true
        end
    end
 
    -- La balle vient de se tourner vers nous : on calcule une fois où elle ira.
    if incoming and not was_incoming then
        react = 10

        -- Où sera le haut de la balle quand son bord droit (x + 8) touchera la raquette (x = 216) ?
        local p = ball.position.y + ball.velocity.y * (208 - ball.position.x) / ball.velocity.x

        -- Les rebonds sur les murs replient la trajectoire entre BALL_MIN_Y et BALL_MAX_Y
        -- (aller-retour = 2 * BALL_SPAN).
        p = (((p - BALL_MIN_Y) % (2 * BALL_SPAN)) + 2 * BALL_SPAN) % (2 * BALL_SPAN)
        if p > BALL_SPAN then
            p = 2 * BALL_SPAN - p
        end
        p = p + BALL_MIN_Y

        -- Point d'impact visé : le centre de la balle face à un point de la raquette.
        local aim = math.rand(-10, 10)
        if math.rand(0, 7) == 0 then
            -- Une balle sur huit : elle se trompe franchement.
            if math.rand(0, 1) == 0 then
                aim = 30
            else
                aim = -30
            end
        end
        target = p - 12 + aim
    end
    was_incoming = incoming

    -- Au repos : retour au centre, avec un léger balancement (sin est en Q8).
    if not incoming then
        target = 56 + math.sin(scene.frame * 3) * 16 / 256
    end

    if react > 0 then
        react = react - 1
    else
        -- Déplacement physique : les murs de la carte arrêtent la raquette.
        local step = math.clamp((target - self.position.y) / 4, -2, 2)
        self.velocity = vec2(0, step * 256)
        self:apply_velocity()
    end

    if hit_t < 99 then
        hit_t = hit_t + 1
    end
    self:stretch(hit_t, 12, 30)
    self:wobble(hit_t, 18, 6)
end

function on_collision_enter(other, my_box, other_box)
    hit_t = 0
end
