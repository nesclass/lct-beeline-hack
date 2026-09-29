import { mount } from 'svelte';
import 'leaflet/dist/leaflet.css';
import './tokens.css';
import './app.css';
import App from './App.svelte';

mount(App, { target: document.getElementById('app') });
