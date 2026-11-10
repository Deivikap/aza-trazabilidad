from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group

from .models import Batch, Lote, Receta
from .roles import ROLES

User = get_user_model()


class ObservacionForm(forms.Form):
    contenido = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
                                label="Observación operativa")

    def clean_contenido(self):
        v = self.cleaned_data["contenido"].strip()
        if not v:
            raise forms.ValidationError("La observación no puede estar vacía.")
        return v  # el escape anti-XSS lo aplica la plantilla al mostrarla


class UsuarioForm(forms.Form):
    username = forms.CharField(max_length=50, label="Usuario")
    first_name = forms.CharField(max_length=100, label="Nombre")
    email = forms.EmailField(label="Correo")
    rol = forms.ChoiceField(choices=[(r, r) for r in ROLES])
    password = forms.CharField(widget=forms.PasswordInput, label="Contraseña (mín. 12 caracteres)")

    def clean_username(self):
        u = self.cleaned_data["username"]
        if User.objects.filter(username=u).exists():
            raise forms.ValidationError("Ya existe ese usuario.")
        return u

    def clean_password(self):
        p = self.cleaned_data["password"]
        password_validation.validate_password(p)
        return p

    def guardar(self):
        d = self.cleaned_data
        u = User.objects.create_user(d["username"], d["email"], d["password"], first_name=d["first_name"])
        u.groups.add(Group.objects.get(name=d["rol"]))
        return u


class RecetaForm(forms.ModelForm):
    class Meta:
        model = Receta
        fields = ["codigo", "nombre", "tol_angular_min", "tol_angular_max", "activa"]


class LoteForm(forms.ModelForm):
    class Meta:
        model = Lote
        fields = ["codigo", "estado"]


class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ["codigo", "lote", "receta", "estado"]
