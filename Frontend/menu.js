// Menú del botón de hamburguesa (se carga en todas las páginas, después de api.js)
document.addEventListener('DOMContentLoaded', () => {
    const button = document.querySelector('.menu-btn');
    if (!button) return;

    const panel = document.createElement('nav');
    panel.className = 'menu-panel';
    document.body.append(panel);

    function link(text, href) {
        const a = document.createElement('a');
        a.textContent = text;
        a.href = href;
        return a;
    }

    function build() {
        const items = [link('Inicio', 'index.html'), link('Productos', 'productos.html')];

        if (isLoggedIn()) {
            items.push(link('Mi cuenta', 'cuenta.html'));

            const logout = document.createElement('button');
            logout.textContent = 'Cerrar sesión';
            logout.onclick = () => {
                clearSession();
                location.href = 'index.html';
            };
            items.push(logout);
        } else {
            items.push(link('Ingresar / Crear cuenta', 'cuenta.html'));
        }

        panel.replaceChildren(...items);
    }

    button.setAttribute('aria-expanded', 'false');
    button.onclick = () => {
        build();
        const open = panel.classList.toggle('open');
        button.setAttribute('aria-expanded', String(open));
    };

    // Se cierra al hacer clic fuera del menú
    document.addEventListener('click', event => {
        if (!panel.contains(event.target) && !button.contains(event.target)) {
            panel.classList.remove('open');
            button.setAttribute('aria-expanded', 'false');
        }
    });
});
