function on_start()
    interface:get("Invitation"):draw("titre_invitation")
end

function on_update()
    if input:pressed("a") then
        scene:switch("Niveau")
    end
end
