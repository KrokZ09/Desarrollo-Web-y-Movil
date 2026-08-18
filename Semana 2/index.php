<!DOCTYPE html>
<html lang="es">
    <head>
        <title>Pagina Principal</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js"></script>    
    </head>
    <body>
        <!-- Navbar -->
         <nav class="navbar navbar-expand-sm bg-dark navbar-dark">
            <div class="container-fluid">
                <a class="navbar-brand" href="index.php">Logo</a>
                    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#collapsibleNavbar">
                        <span class="navbar-toggler-icon"></span>
                    </button>
                    <div class="collapse navbar-collapse" id="collapsibleNavbar">
                        <ul class="navbar-nav">
                            <li class="nav-item dropdown">
                                <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">NombreEmpresa</a>
                                <ul class="dropdown-menu">
                                    <li><a class="dropdown-item" href="quienes_somos.php">Quienes somos</a></li>
                                    <li><a class="dropdown-item" href="#">algo</a></li>
                                    <li><a class="dropdown-item" href="#">algo</a></li>
                                </ul>
                            </li>
                            <li class="nav-item">
                                <a class="nav-link" href="titulos.php">Titulos</a>
                            </li>
                            <li class="nav-item">
                                <a class="nav-link" href="redes.php">Redes</a>
                            </li>
                        </ul>
                    </div>
                </div>
            </nav>

        <!-- Container -->
         <div class="container-fluid">
            <h1>Pagina Principal</h1><br>
            <a href="index.php">Ir a Principal</a><br>
            <a href="titulos.php">Ir a Titulos</a><br>
            <a href="quienes_somos.php">Ir a Quienes somos</a><br>
            <a href="redes.php">Ir a Redes</a><br>
        </div>
        <!-- Footer -->
         <div class="container-fluid bg-success">
            <div class="row">
                <div class="col-4"></div>
                <div class="col-4 d-flex justify-content-center"><strong>Empresa@algo.algo</strong></div>
                <div class="col-4"></div>
            </div>
        </div>
         <!-- Modal -->
    </body>
</html>