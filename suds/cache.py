# This program is free software; you can redistribute it and/or modify it under
# the terms of the (LGPL) GNU Lesser General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Library Lesser General Public License
# for more details at ( http://www.gnu.org/licenses/lgpl.html ).
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
# written by: Jeff Ortel ( jortel@redhat.com )

"""
Basic caching classes.

"""

import suds
import suds.sax.element
import suds.sax.parser

import datetime
import os
try:
    import cPickle as pickle
except Exception:
    import pickle
import tempfile

from logging import getLogger
log = getLogger(__name__)


class Cache(object):
    """An object cache."""

    def get(self, id):
        """
        Get an object from the cache by id.

        @param id: The object id.
        @type id: str
        @return: The object, else None.
        @rtype: any

        """
        raise Exception("not-implemented")

    def put(self, id, object):
        """
        Put an object into the cache.

        @param id: The object id.
        @type id: str
        @param object: The object to add.
        @type object: any

        """
        raise Exception("not-implemented")

    def purge(self, id):
        """
        Purge an object from the cache by id.

        @param id: A object id.
        @type id: str

        """
        raise Exception("not-implemented")

    def clear(self):
        """Clear all objects from the cache."""
        raise Exception("not-implemented")


class NoCache(Cache):
    """The pass-through object cache."""

    def get(self, id):
        return

    def put(self, id, object):
        pass


class FileCache(Cache):
    """
    A file-based URL cache.

    @cvar fnprefix: The file name prefix.
    @type fnprefix: str
    @ivar duration: The duration after which cached entries expire (0=never).
        Unit may be: (months|weeks|days|hours|minutes|seconds).
    @type duration: (unit, value)
    @ivar location: The cached file folder.
    @type location: str

    """
    fnprefix = "suds"
    units = ("months", "weeks", "days", "hours", "minutes", "seconds")

    def __init__(self, location=None, **duration):
        """
        @param location: The cached file folder.
        @type location: str
        @param duration: The duration after which cached entries expire
            (0=never). Unit may be: (months|weeks|days|hours|minutes|seconds).
        @type duration: {unit: value}

        """
        if location is None:
            location = os.path.join(tempfile.gettempdir(), "suds")
        self.location = location
        self.duration = (None, 0)
        self.__set_duration(**duration)
        self.__check_version()

    def clear(self):
        for filename in os.listdir(self.location):
            path = os.path.join(self.location, filename)
            if os.path.isdir(path):
                continue
            if filename.startswith(self.fnprefix):
                os.remove(path)
                log.debug("deleted: %s", path)

    def fnsuffix(self):
        """
        Get the file name suffix.

        @return: The suffix.
        @rtype: str

        """
        return "gcf"

    def get(self, id):
        try:
            f = self._getf(id)
            try:
                return f.read()
            finally:
                f.close()
        except Exception:
            pass

    def purge(self, id):
        filename = self.__filename(id)
        try:
            os.remove(filename)
        except Exception:
            pass

    def put(self, id, data):
        try:
            filename = self.__filename(id)
            f = self.__open(filename, "wb")
            try:
                f.write(data)
            finally:
                f.close()
            return data
        except Exception:
            log.debug(id, exc_info=1)
            return data

    def _getf(self, id):
        """Open a cached file with the given id for reading."""
        try:
            filename = self.__filename(id)
            self.__remove_if_expired(filename)
            return self.__open(filename, "rb")
        except Exception:
            pass

    def __check_version(self):
        path = os.path.join(self.location, "version")
        try:
            f = self.__open(path)
            try:
                version = f.read()
            finally:
                f.close()
            if version != suds.__version__:
                raise Exception()
        except Exception:
            self.clear()
            f = self.__open(path, "w")
            try:
                f.write(suds.__version__)
            finally:
                f.close()

    def __filename(self, id):
        """Return the cache file name for an entry with a given id."""
        suffix = self.fnsuffix()
        filename = "%s-%s.%s" % (self.fnprefix, id, suffix)
        return os.path.join(self.location, filename)

    def __mktmp(self):
        """Create the I{location} folder if it does not already exist."""
        try:
            if not os.path.isdir(self.location):
                os.makedirs(self.location)
        except Exception:
            log.debug(self.location, exc_info=1)
        return self

    def __open(self, filename, *args):
        """Open cache file making sure the I{location} folder is created."""
        self.__mktmp()
        return open(filename, *args)

    def __remove_if_expired(self, filename):
        """
        Remove a cached file entry if it expired.

        @param filename: The file name.
        @type filename: str

        """
        if self.duration[1] < 1:
            return
        created = datetime.datetime.fromtimestamp(os.path.getctime(filename))
        d = {self.duration[0]: self.duration[1]}
        expired = created + datetime.timedelta(**d)
        if expired < datetime.datetime.now():
            os.remove(filename)
            log.debug("%s expired, deleted", filename)

    def __set_duration(self, **duration):
        """
        Set the duration after which cached entries expire.

        @param duration: The duration after which cached entries expire
            (0=never). Unit may be: (months|weeks|days|hours|minutes|seconds).
        @type duration: {unit: value}

        """
        if len(duration) == 1:
            arg = duration.items()[0]
            if not arg[0] in self.units:
                raise Exception("must be: %s" % str(self.units))
            self.duration = arg
        return self


class DocumentCache(FileCache):
    """XML document file cache."""

    def fnsuffix(self):
        return "xml"

    def get(self, id):
        fp = None
        try:
            fp = self._getf(id)
            if fp is None:
                return None
            p = suds.sax.parser.Parser()
            return p.parse(fp)
        except Exception:
            if fp is not None:
                fp.close()
            self.purge(id)

    def put(self, id, object):
        if isinstance(object, suds.sax.element.Element):
            super(DocumentCache, self).put(id, suds.byte_str(str(object)))
        return object


class ObjectCache(FileCache):
    """
    Pickled object file cache.

    @cvar protocol: The pickling protocol.
    @type protocol: int

    """
    protocol = 2

    def fnsuffix(self):
        return "px"

    def get(self, id):
        fp = None
        try:
            fp = self._getf(id)
            if fp is not None:
                return pickle.load(fp)
        except Exception:
            if fp is not None:
                fp.close()
            self.purge(id)

    def put(self, id, object):
        data = pickle.dumps(object, self.protocol)
        super(ObjectCache, self).put(id, data)
        return object
