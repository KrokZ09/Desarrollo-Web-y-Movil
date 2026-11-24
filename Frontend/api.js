// Dirección del API Gateway (la única entrada pública del backend)
const API_URL = 'http://127.0.0.1:8000/api/v1';

// Llama al backend y devuelve el JSON. Si hay error, lanza un Error con el mensaje del servidor.
async function api(path, options = {}) {
    const response = await fetch(API_URL + path, options);

    let data = null;
    try {
        data = await response.json();
    } catch (_) {
        // la respuesta no tenía cuerpo JSON
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
