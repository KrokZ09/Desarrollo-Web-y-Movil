const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');

const {ApolloServer, gql} = require('apollo-server-express');
const Usuario = require('./models/usuario')

mongoose.connect('mongodb://localhost:27017/DesarrolloWebSemana5')
const TypeDefs = gql`
    type Usuario{
        id: ID!
        nombre: String!
        pass: String!
    }
    input UsuarioInput{
        nombre: String!
        pass: String!
    }
`;