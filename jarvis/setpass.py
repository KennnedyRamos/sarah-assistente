"""Define ou troca a senha de acesso: python -m jarvis.setpass"""
import getpass
import sys

from . import auth, db

db.init()
if "--if-missing" in sys.argv and auth.password_configured():
    sys.exit(0)
print("Defina a senha da Sarah (mínimo 10 caracteres). Ela será exigida no PC e no celular.")
while True:
    first = getpass.getpass("Nova senha: ")
    if getpass.getpass("Repita a senha: ") != first:
        print("As senhas não conferem. Tente de novo.")
        continue
    try:
        auth.set_password(first)
    except ValueError as e:
        print(e)
        continue
    print("Senha salva. Todas as sessões anteriores foram encerradas.")
    break
