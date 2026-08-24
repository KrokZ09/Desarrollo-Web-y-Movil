<!DOCTYPE html>
<html lang="es">
    <head>
        <title>Privado</title>
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
                    <button type="button" class="btn btn-success" data-bs-toggle="modal" data-bs-target="#myModal">Login</button>
                </div>
            </nav>

        <!-- Container -->
         <div class="container-fluid">
            <h1>Privado</h1><br>
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
        <div class="modal fade" id="myModal">
            <div class="modal-dialog">
                <div class="modal-content">
                    <!-- Modal Header -->
                    <div class="modal-header">
                        <h4 class="modal-title">Autenticar</h4>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>

                    <!-- Modal body -->
                    <div class="modal-body">
                        <form action="privado.php">
                            <div class="mb-2 mt-2">
                                <label for="email" class="form-label">Correo electrónico:</label>
                                <input type="email" class="form-control" id="email" placeholder="Introducir correo" name="email">
                            </div>
                            <div class="mb-2">
                                <label for="pwd" class="form-label">Contraseña:</label>
                                <input type="password" class="form-control" id="pwd" placeholder="Introducir contraseña" name="pswd">
                            </div>
                            <div class="form-check mb-2">
                                <label class="form-check-label">
                                <input class="form-check-input" type="checkbox" name="remember"> Recuerdame
                                </label>
                            </div>
                            <button type="submit" class="btn btn-primary">Login</button>
                        </form>
                    </div>

                    <!-- Modal footer -->
                    <div class="modal-footer">
                        <button type="button" class="btn btn-danger" data-bs-dismiss="modal">Cancelar</button>
                    </div>
                </div>
            </div>
        </div>
    </body>
</html>