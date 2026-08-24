const usuarios = {
    cristobal: "1234",
    juan: "abcd",
    pedro: "a1b2"
};

const formulario = document.getElementById("loginForm");

formulario.addEventListener("submit", function(event) {

    event.preventDefault();

    const correo = document.getElementById("email").value;
    const contraseña = document.getElementById("pwd").value;

    if (usuarios[correo] === contraseña){
        window.location.href = "privado.php";
    } else {
        alert("Correo o contraseña invalidos")
    }

});