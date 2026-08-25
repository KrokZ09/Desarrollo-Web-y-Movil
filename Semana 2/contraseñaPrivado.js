const usuarios = {
    "cristobal@xd": "1234",
    "juan@xd": "abcd",
    "pedro@xd": "5678"
};

const formulario = document.getElementById("loginForm");
const mensaje = document.getElementById("mensaje");

formulario.addEventListener("submit", function(event) {

    event.preventDefault();

    const correo = document.getElementById("email").value;
    const contraseña = document.getElementById("pwd").value;

    console.log("Correo:", correo);
    console.log("Contraseña:", contraseña);
    console.log("Contraseña guardada:", usuarios[correo]);

   if (usuarios[correo] === contraseña) {

    mensaje.textContent = "Inicio de sesión correcto";
    mensaje.className = "alert alert-success";

    window.location.href = "privado.php";

    } else {

        mensaje.textContent = "Correo o contraseña incorrectos";
        mensaje.className = "alert alert-danger";

    }
});

const modal = document.getElementById("myModal");

modal.addEventListener("hidden.bs.modal", function () {
    mensaje.textContent = "";
    mensaje.className = "";
});