// Dirección del API Gateway (la única entrada pública del backend)
const API_URL = 'http://127.0.0.1:8000/api/v1';
const TOKEN_KEY = 'nonna_token';

// ---------- Sesión ----------
// El token vive en sessionStorage: se borra al cerrar la pestaña y expira a los 30 minutos.
function getToken() {
    return sessionStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
    sessionStorage.setItem(TOKEN_KEY, token);
}

function clearSession() {
    sessionStorage.removeItem(TOKEN_KEY);
}

// Lee los datos del token SOLO para decidir qué mostrar en pantalla.
// No es seguridad: el backend vuelve a verificar el token en cada llamada.
function tokenPayload() {
    const token = getToken();
    if (!token) return null;
    try {
        const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
        return JSON.parse(atob(part));
    } catch (_) {
        return null;
    }
}

function isLoggedIn() {
    const payload = tokenPayload();
    return !!payload && payload.exp * 1000 > Date.now();
}

function currentRole() {
    const payload = tokenPayload();
    return payload ? payload.role : null;
}

// ---------- Llamadas al backend ----------
// api('/products')
// api('/auth/login', { method: 'POST', body: { email, password } })
// api('/clients/me', { auth: true })   <- envía el token de la sesión
async function api(path, { method = 'GET', body, auth = false } = {}) {
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (auth && getToken()) headers['Authorization'] = 'Bearer ' + getToken();

    const response = await fetch(API_URL + path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
    });

    let data = null;
    try {
        data = await response.json();
    } catch (_) {
        // la respuesta no tenía cuerpo JSON
    }

    if (response.status === 401 && auth) {
        clearSession();
        throw new Error('Tu sesión expiró. Ingresa de nuevo.');
    }
    if (!response.ok) {
        throw new Error((data && data.detail) || 'Error ' + response.status);
    }
    return data;
}

// 5900 -> "$5.900"
function formatPrice(value) {
    return '$' + Number(value).toLocaleString('es-CL');
}
