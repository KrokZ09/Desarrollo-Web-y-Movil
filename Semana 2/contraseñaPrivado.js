const usuarios = {
    "cristobal@xd": "1234",
    "juan@xd": "abcd",
    "pedro@xd": "a1b2"
};

const formulario = document.getElementById("loginForm");

formulario.addEventListener("submit", function(event) {
    event.preventDefault();

    const correo = document.getElementById("email").value;
    const contraseña = document.getElementById("pwd").value;

    console.log("Correo ingresado:", correo);
    console.log("Contraseña ingresada:", contraseña);
    console.log("Contraseña guardada:", usuarios[correo]);

    if (usuarios[correo] === contraseña) {
        alert("Login correcto");
        window.location.href = "privado.php";
    } else {
        alert("Correo o contraseña inválidos");
    }
});