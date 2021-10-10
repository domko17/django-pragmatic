import importlib
import inspect
import pkgutil
import re
import sys


import django_filters
from django.apps import apps


class MissingTestMixin(object):
    CHECK_MODULES = []  # where to look for objects and methods that should be tested, override this, eg. [app.sub_app_1, app.sub_app_2]
    EXCLUDE_MODULES = ['migrations', 'commands', 'tests', 'settings']   # where not to look for objects and methods that should be tested

    @property
    def apps_to_check(self):
        return [app.name for app in apps.get_app_configs() if app.name.startswith(tuple(self.CHECK_MODULES))]

    def get_tests_by_module(self, parent_module_names=[], submodule_name='tests'):
        # returns method names of test classes
        if not parent_module_names:
            parent_module_names = self.CHECK_MODULES

        module_names = self.get_submodule_names(parent_module_names, submodule_name)
        tests = set()

        for module_name in module_names:
            try:
                if module_name not in sys.modules.keys():
                    importlib.import_module(module_name)
                module = sys.modules[module_name]
            except:
                print(module_name)
                raise
            else:
                tests |= {method for method in self.get_module_class_methods(module) if
                          method.__name__.startswith('test_')}

        return tests

    def get_module_class_methods(self, module):
        # get classes defined in module, not imported
        classes = self.get_module_classes(module)
        methods = set()

        for cls in classes:
            methods |= {value for value in cls.__dict__.values() if callable(value)}

        return methods

    def get_module_classes(self, module):
        return {m[1] for m in inspect.getmembers(module, inspect.isclass) if m[1].__module__ == module.__name__}

    def get_module_functions(self, module):
        return {m[1] for m in inspect.getmembers(module, inspect.isfunction) if m[1].__module__ == module.__name__}

    def get_submodule_names(self, parent_module_names, submodule_names, exclude_names=[]):
        # looks for submodules of parent_module containing submodule_name and not containing any of exclude_names,
        # which are not package (files, not dirs)
        module_names = set()

        if isinstance(parent_module_names, str):
            parent_module_names = [parent_module_names]

        if isinstance(submodule_names, str):
            submodule_names = [submodule_names]

        if isinstance(exclude_names, str):
            exclude_names = [exclude_names]

        for parent_module_name in parent_module_names:
            parent_module = sys.modules[parent_module_name]

            for importer, modname, ispkg in pkgutil.walk_packages(path=parent_module.__path__,
                                                                  prefix=parent_module.__name__ + '.',
                                                                  onerror=lambda x: None):

                for submodule_name in submodule_names:
                    if submodule_name in modname and not ispkg:
                        if not any([exclude_name in modname for exclude_name in exclude_names]):
                            module_names.add(modname)

        return (module_names)

    def test_for_missing_filters(self):
        module_names = self.get_submodule_names(self.CHECK_MODULES, 'filters', self.EXCLUDE_MODULES)
        filter_classes = set()

        # get filter classes
        for module_name in module_names:
            try:
                if module_name not in sys.modules.keys():
                    importlib.import_module(module_name)
                module = sys.modules[module_name]
            except:
                print(module_name)
                raise
            else:
                filter_classes |= {
                    cls for cls in self.get_module_classes(module) if \
                        issubclass(cls, (django_filters.FilterSet, django_filters.Filter)) or \
                        any([key.startswith('filter') for key, value in cls.__dict__.items() if callable(value)])
                }

        # get all filter tests names and divide to class/mothod tets subsets
        test_names = {test.__name__[5:] for test in self.get_tests_by_module(submodule_name='tests.test_filters')}
        filter_classes_tests = {name for name in test_names if name.endswith(('filter', 'filter_set', 'mixin'))}
        filter_methods_tests = test_names - filter_classes_tests

        # get class/method names out of test names
        tested_class_names = {''.join([w.capitalize() for w in name.split('_')]) for name in filter_classes_tests}
        tested_method_names = set()

        for name in filter_methods_tests:
            if 'filter_set' in name:
                class_name, method_name = name.split('_filter_set_')
                class_name = ''.join([w.capitalize() for w in class_name.split('_')]) + 'FilterSet'
            else:
                class_name, method_name = name.split('_filter_')
                class_name = ''.join([w.capitalize() for w in class_name.split('_')]) + 'Filter'
                method_name = 'filter_' + method_name

            tested_method_names.add('.'.join([class_name, method_name]))

        for cls in filter_classes:
            # test filter class test existence
            self.assertTrue(cls.__name__ in tested_class_names, f'{cls.__module__}.{cls.__name__} test missing')

            # test filter class methods tests existence
            if issubclass(cls, django_filters.FilterSet):
                filter_methods_names = {f'{cls.__name__}.{key}' for key, value in cls.__dict__.items() if callable(value) and key.startswith('filter')}
                not_tested_methods = filter_methods_names - tested_method_names
                self.assertEqual(not_tested_methods, set(), f'missing tests for {not_tested_methods}')

    def test_for_missing_managers(self):
        module_names = self.get_submodule_names(self.CHECK_MODULES, ['managers', 'querysets'], self.EXCLUDE_MODULES)
        manager_classes = set()

        # get manager classes
        for module_name in module_names:
            try:
                if module_name not in sys.modules.keys():
                    importlib.import_module(module_name)
                module = sys.modules[module_name]
            except:
                print(module_name)
                raise
            else:
                manager_classes |= self.get_module_classes(module)

        # get all manager tests names
        test_names = {test.__name__.replace('test_', '') for test in self.get_tests_by_module(submodule_name='tests.test_managers') if test.__name__.endswith(('manager', 'queryset'))}

        # get class/method names out of test names
        tested_class_names = {''.join([word.capitalize() for word in test.split('_')]).replace('Queryset', 'QuerySet') for test in test_names}

        for cls in manager_classes:
            # test filter class test existence
            self.assertTrue(cls.__name__ in tested_class_names, f'{cls.__module__}.{cls.__name__} test missing')

        for app_name in self.apps_to_check:
            managers_to_test = set()

            for dir_name in ['managers', 'querysets']:
                module_name = '.'.join([app_name, dir_name])

                try:
                    importlib.import_module(module_name)
                    module = sys.modules[module_name]
                except (ModuleNotFoundError, KeyError):
                    pass
                else:
                    # get only classes defined in the file, not imported
                    managers_to_test |= {m[0] for m in inspect.getmembers(module, inspect.isclass) if m[1].__module__ == module.__name__}

            try:
                # test modules may not be loaded, therefore import
                importlib.import_module('.'.join([app_name, 'tests.test_managers']))
            except ImportError:
                if managers_to_test:
                    # mangers exist but tests not
                    self.fail(f'Missing manager tests for app {app_name}')
            else:
                if not managers_to_test:
                    pass
                    # managers doesn't exist but tests yes
                    # self.fail(f'there is test_managers file without managers/querysets file in app{app_name}')
                else:
                    # managers and tests exists
                    # get test managers module
                    module = sys.modules['.'.join([app_name, 'tests.test_managers'])]

                    # get test manager classes, only classes defined in module, not imported
                    test_classes = {m[1] for m in inspect.getmembers(module, inspect.isclass) if m[1].__module__ == module.__name__}

                    for cls in test_classes:
                        # get managers testing methods by name
                        tests = [func for func in cls.__dict__.keys() if
                                 callable(getattr(cls, func)) and func.startswith("test_") and func.endswith(('manager', 'queryset'))]

                        # convert test methods names to manager/queryset clasess: test_name_of_manager -> NameOfManager, test_name_of_queryset -> NameOfQuerySet
                        tested_managers = {
                        ''.join([word.capitalize() for word in test.replace('test_', '').split('_')]).replace(
                            'Queryset', 'QuerySet') for test in tests}

                        missing_managers = managers_to_test - tested_managers
                        self.assertEqual(managers_to_test, tested_managers, f'Missing managers for app {app_name}: {missing_managers}')

    def test_for_missing_signals(self):
        module_names = self.get_submodule_names(self.CHECK_MODULES, ['signals'], self.EXCLUDE_MODULES)
        signals = set()

        # get signal classes
        for module_name in module_names:
            try:
                if module_name not in sys.modules.keys():
                    importlib.import_module(module_name)
                module = sys.modules[module_name]
            except:
                print(module_name)
                raise
            else:
                signals |= self.get_module_functions(module)

        signal_names = {'.'.join((signal.__module__, signal.__name__)) for signal in signals}

        # get all signal tests names
        test_names = {'.'.join((test.__module__.replace('tests.test_signals', 'signals'), test.__name__.replace('test_', '', 1))) for test in
                      self.get_tests_by_module(submodule_name='tests.test_signals')}

        self.assertEqual(signal_names, test_names, f'Signals not matching: {sorted(signal_names ^ test_names)}')

    def test_for_commented_asserts(self):
        # check that no "self.assert..." are left commented after updating/debugging
        exclude_modules = [m for m in self.EXCLUDE_MODULES if m != 'tests']
        module_names = self.get_submodule_names(self.CHECK_MODULES, ['tests'], exclude_modules)
        commented_asserts = set()

        for module_name in module_names:
            try:
                if module_name not in sys.modules.keys():
                    importlib.import_module(module_name)
                module = sys.modules[module_name]

                # code = inspect.getsource(module)
                lines, start_index = inspect.getsourcelines(module)
            except:
                print(module_name)
                raise

            for i, line in enumerate(lines):
                matches = re.finditer(r'\# ?self\.assert', line)
                for match in matches:
                    commented_asserts.add((line, module_name, f'line {i + start_index + 1}'))

        commented_asserts = sorted(commented_asserts, key=lambda x: x[0])

        self.assertEqual(commented_asserts, [], f'There are som commented asserts')

    def test_for_missing_permissions(self):
        explicit_permission_occurances = self.get_explicit_permissions_by_module(parent_module_names=self.CHECK_MODULES, submodule_names=self.CHECK_MODULES, exclude=self.EXCLUDE_MODULES)
        explicit_permissions = {}
        tested_permissions = {}

        # get occurances of permissions in code and structure into dict
        for name, path, line in explicit_permission_occurances:
            if name not in explicit_permissions:
                explicit_permissions[name] = {}
                tested_permissions[name] = {}

            if path not in explicit_permissions[name]:
                explicit_permissions[name][path] = []
                tested_permissions[name][path] = []

            explicit_permissions[name][path].append(line)

        tests = self.get_tests_by_module(submodule_name='tests.test_permissions')

        # get permission tests, derive location of tested permission occurance from test name and put into dict
        for test in tests:
            permission_name = re.findall(r'permission = \'[a-z]+.[a-z_]+\'', inspect.getsource(test))[0].replace('permission = ', '')[1:-1]
            path = re.findall(r'permission_path = \'[a-z_.]+\'', inspect.getsource(test))
            path = path[0].replace('permission_path = ', '')[1:-1] if path else None

            if path not in sys.modules:
                module_name = 'swida.portal.' if 'swida.portal.' in test.__module__ else 'swida.core.'
                test_name = test.__name__.replace('test_', module_name)
                print(test_name)
                path = test_name[:test_name.rfind('.')]

                for i in range(1, test_name.count('_') + 2):
                    new_path = test_name.replace('_', '.', i)
                    new_path = new_path[:new_path.rfind('.')]

                    if path == new_path:
                        # all underscores replaced, include ending word
                        new_path = test_name.replace('_', '.', i)

                    # try to include next underscore, to look for files with underscore in name
                    alternative_path = test_name.replace('_', '.', i+1)
                    alternative_path = alternative_path[:alternative_path.rfind('.')]
                    alternative_path = '_'.join(alternative_path.rsplit('.', 1))

                    if new_path in sys.modules:
                        path = new_path
                    elif alternative_path in sys.modules:
                        path = alternative_path
                    else:
                        break

            if permission_name not in tested_permissions:
                tested_permissions[permission_name] = {}
                explicit_permissions[permission_name] = {}

            if not any([exclude_name in path for exclude_name in self.EXCLUDE_MODULES]):
                tested_permissions[permission_name][path].append(test.__name__)

        for permission_name, locations in explicit_permissions.items():
            for path, lines in locations.items():
                self.assertEqual(
                    len(lines),
                    len(tested_permissions[permission_name][path]),
                    f'Missing test for permission "{permission_name}" in "{path}", lines {lines}. \n Tests found: {sorted(tested_permissions[permission_name])}'
                )

                del tested_permissions[permission_name][path]

        surplus_tests = []
        for tests in tested_permissions[permission_name].values():
            surplus_tests.extend(tests)
            self.assertEqual(
                surplus_tests,
                [],
                f'Surplus tests found: {surplus_tests}'
            )

    def get_explicit_permissions_by_module(self, parent_module_names, submodule_names, exclude):
        module_names = self.get_submodule_names(parent_module_names, submodule_names, exclude)

        permissions = set()
        for module_name in module_names:
            try:
                if module_name not in sys.modules.keys():
                    importlib.import_module(module_name)
                module = sys.modules[module_name]

                # code = inspect.getsource(module)
                lines, start_index = inspect.getsourcelines(module)
            except:
                print(module_name)
                raise

            for i, line in enumerate(lines):
                matches = re.finditer(r'has_perm\(\'[a-z]+.[a-z_]+', line)
                for match in matches:
                    if re.match(r' +\#', line) is None:
                        # not commented line
                        permissions.add((match.group(0).replace("has_perm('", ""), module_name, f'line {i + start_index + 1}'))

                matches = re.finditer(r'permission = \'[a-z]+.[a-z_]+', line)
                for match in matches:
                    if re.match(r' +\#', line) is None:
                        # not commented line
                        permissions.add((match.group(0).replace("permission = '", ""), module_name, f'line {i + start_index + 1}'))

                matches = re.finditer(r'\.is_superuser', line)
                for match in matches:
                    if re.match(r' +\#', line) is None:
                        # not commented line
                        permissions.add(('is_superuser', module_name, f'line {i + start_index + 1}'))

        return sorted(permissions, key=lambda x: x[0])
