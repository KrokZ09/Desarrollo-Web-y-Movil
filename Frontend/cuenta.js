document.addEventListener('DOMContentLoaded', () => {
    const guestView = document.querySelector('#guestView');
    const memberView = document.querySelector('#memberView');
    const profileBox = document.querySelector('#profile');
    const loginForm = document.querySelector('#loginForm');
    const registerForm = document.querySelector('#registerForm');

    function setMessage(form, text) {
        form.querySelector('.form-msg').textContent = text;
    }

    function showGuest() {
        guestView.hidden = false;
        memberView.hidden = true;
    }

    function addLine(label, value) {
        const line = document.createElement('p');
        const strong = document.createElement('strong');
        strong.textContent = label + ' ';
        line.append(strong, document.createTextNode(value || '—'));
        profileBox.append(line);
    }

    async function showMember() {
        guestView.hidden = true;
        memberView.hidden = false;
        profileBox.replaceChildren();

        if (currentRole() === 'admin') {
            addLine('Sesión:', 'administración');
            return;
        }

        try {
            const profile = await api('/clients/me', { auth: true });
            addLine('Nombre:', profile.nombre);
            addLine('Correo:', profile.email);
            addLine('Teléfono:', profile.telefono);
        } catch (error) {
            if (!isLoggedIn()) {
                showGuest();
                setMessage(loginForm, error.message);
            } else {
                profileBox.textContent = error.message;
            }
        }
    }

    async function login(email, password) {
        const data = await api('/auth/login', { method: 'POST', body: { email, password } });
        setToken(data.accessToken);
    }

    // Deshabilita el botón mientras se espera la respuesta y muestra los errores del servidor
    async function submit(form, action) {
        const button = form.querySelector('button[type="submit"]');
        button.disabled = true;
        setMessage(form, '');
        try {
            await action(Object.fromEntries(new FormData(form)));
            form.reset();
            await showMember();
        } catch (error) {
            setMessage(form, error.message);
        } finally {
            button.disabled = false;
        }
    }

    loginForm.addEventListener('submit', event => {
        event.preventDefault();
        submit(loginForm, values => login(values.email, values.password));
    });

    registerForm.addEventListener('submit', event => {
        event.preventDefault();
        submit(registerForm, async values => {
            const body = { nombre: values.nombre, email: values.email, password: values.password };
            if (values.telefono) body.telefono = values.telefono;
            await api('/auth/register', { method: 'POST', body });
            await login(values.email, values.password);
        });
    });

    document.querySelector('#logoutBtn').onclick = () => {
        clearSession();
        showGuest();
    };

    if (isLoggedIn()) {
        showMember();
    } else {
        clearSession();
        showGuest();
    }
});
