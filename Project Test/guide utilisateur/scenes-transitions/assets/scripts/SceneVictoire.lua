function on_start()
    interface:get("Message"):draw("victoire_message")
end

function on_update()
    if input:pressed("a") then
        scene:switch("Titre")
    end
end
