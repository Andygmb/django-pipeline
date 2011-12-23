import os
import urlparse

from django.core.files.base import ContentFile

from pipeline.conf import settings
from pipeline.compilers import Compiler
from pipeline.compressors import Compressor
from pipeline.glob import glob
from pipeline.signals import css_compressed, js_compressed
from pipeline.storage import storage


class Package(object):
    def __init__(self, config):
        self.config = config
        self._sources = []

    @property
    def sources(self):
        if not self._sources:
            paths = []
            for pattern in self.config.get('source_filenames', []):
                for path in glob(pattern):
                    if not path in paths:
                        paths.append(str(path))
            self._sources = paths
        return self._sources

    @property
    def paths(self):
        return [path for path in self.sources
            if not path.endswith(settings.PIPELINE_TEMPLATE_EXT)]

    @property
    def templates(self):
        return [path for path in self.sources
            if path.endswith(settings.PIPELINE_TEMPLATE_EXT)]

    @property
    def output_filename(self):
        return self.config.get('output_filename')

    @property
    def extra_context(self):
        return self.config.get('extra_context', {})

    @property
    def template_name(self):
        return self.config.get('template_name')

    @property
    def variant(self):
        return self.config.get('variant')

    @property
    def manifest(self):
        return self.config.get('manifest', True)

    @property
    def absolute_paths(self):
        return self.config.get('absolute_paths', True)


class Packager(object):
    def __init__(self, verbose=False, css_packages=None, js_packages=None):
        self.verbose = verbose
        self.compressor = Compressor(verbose)
        self.compiler = Compiler(verbose)
        if css_packages is None:
            css_packages = settings.PIPELINE_CSS
        if js_packages is None:
            js_packages = settings.PIPELINE_JS
        self.packages = {
            'css': self.create_packages(css_packages),
            'js': self.create_packages(js_packages),
        }

    def package_for(self, kind, package_name):
        try:
            return self.packages[kind][package_name]
        except KeyError:
            raise PackageNotFound(
                "No corresponding package for %s package name : %s" % (
                    kind, package_name
                )
            )

    def individual_url(self, filename):
        relative_path = self.compressor.relative_path(filename)[1:]
        relative_url = relative_path.replace(os.sep, '/')
        return urlparse.urljoin(settings.PIPELINE_URL,
            relative_url)

    def pack_stylesheets(self, package, **kwargs):
        return self.pack(package, self.compressor.compress_css, css_compressed,
            variant=package.variant, absolute_paths=package.absolute_paths,
            **kwargs)

    def compile(self, paths):
        return self.compiler.compile(paths)

    def pack(self, package, compress, signal, **kwargs):
        output_filename = package.output_filename
        if self.verbose:
            print "Saving: %s" % output_filename
        paths = self.compile(package.paths)
        content = compress(paths,
            asset_url=self.individual_url(output_filename), **kwargs)
        self.save_file(output_filename, content)
        signal.send(sender=self, package=package, **kwargs)
        return output_filename

    def pack_javascripts(self, package, **kwargs):
        return self.pack(package, self.compressor.compress_js, js_compressed, templates=package.templates, **kwargs)

    def pack_templates(self, package):
        return self.compressor.compile_templates(package.templates)

    def save_file(self, path, content):
        return storage.save(path, ContentFile(content))

    def create_packages(self, config):
        packages = {}
        if not config:
            return packages
        for name in config:
            packages[name] = Package(config[name])
        return packages


class PackageNotFound(Exception):
    pass
