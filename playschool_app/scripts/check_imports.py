import importlib.util


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    print(name, 'loaded')


if __name__ == '__main__':
    load('app/secrets_manager.py', 'secrets_manager_local')
    load('scripts/provision_tenant.py', 'provision_tenant_local')
    print('FILES_OK')
