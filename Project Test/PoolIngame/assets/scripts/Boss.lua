-- Le boss : à la 15e image il perd son bras (la partie Canon), puis son voyant reste allumé.
local t = 0

function on_update()
    t = t + 1
    if t == 15 then
        self.Canon:destroy()
    end
end
