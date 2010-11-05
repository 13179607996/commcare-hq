import itertools
import settings
import shlex
from subprocess import Popen, PIPE
from tempfile import NamedTemporaryFile

class JadDict(dict):
    @classmethod
    def from_jad(cls, jad_contents):
        sep = ": "
        jd = cls()
        if '\r\n' in jad_contents:
            jd.line_ending = '\r\n'
        else:
            jd.line_ending = '\n'
        lines = [line.strip() for line in jad_contents.split(jd.line_ending) if line.strip()]
        for line in lines:
            i = line.find(sep)
            if i == -1:
                pass
            key, value = line[:i], line[i+len(sep):]
            jd[key] = value
        return jd

    def render(self):
        '''Render self as jad file contents'''
        ordered_start = ['MIDlet-Name', 'MIDlet-Version', 'MIDlet-Vendor', 'MIDlet-Jar-URL',
                        'MIDlet-Jar-Size', 'MIDlet-Info-URL', 'MIDlet-1', 'MIDlet-Permissions']
        ordered_end = ['MIDlet-Jar-RSA-SHA1', 'MIDlet-Certificate-1-1',
                        'MIDlet-Certificate-1-2', 'MIDlet-Certificate-1-3',
                        'MIDlet-Certificate-1-4']
        unordered = [key for key in self.keys() if key not in ordered_start and key not in ordered_end]
        props = itertools.chain(ordered_start, sorted(unordered), ordered_end)
        lines = ['%s: %s%s' % (key, self[key], self.line_ending) for key in props if key in self]
        return "".join(lines)

def sign_jar(jad, jar):
    if not (hasattr(jad, 'update') and hasattr(jad, 'render')):
        jad = JadDict.from_jad(jad)

    ''' run jadTool on the newly created JAR '''
    jad_tool    = settings.JAR_SIGN['jad_tool']
    key_store   = settings.JAR_SIGN['key_store']
    key_alias   = settings.JAR_SIGN['key_alias']
    store_pass  = settings.JAR_SIGN['store_pass']
    key_pass    = settings.JAR_SIGN['key_pass']

    # remove traces of former jar signings, if any
    jad.update({
        "MIDlet-Certificate-1-1" : None,
        "MIDlet-Certificate-1-2" : None,
        "MIDlet-Certificate-1-3" : None,
        "MIDlet-Jar-RSA-SHA1" : None,
        "MIDlet-Permissions" : None
    })
    line_ending = jad.line_ending
    # save jad and jar to actual files
    with NamedTemporaryFile('w', suffix='.jad') as jad_file:
        with NamedTemporaryFile('w', suffix='.jar') as jar_file:

            jad_file.write(jad.render())
            jar_file.write(jar)

            jad_file.flush()
            jar_file.flush()
#            with open(jar_file.name) as f:
#                new_jar = f.read()
#                assert(jar == new_jar)
#                print len(new_jar)


            step_one = "java -jar %s -addjarsig -jarfile %s -alias %s -keystore %s -storepass %s -keypass %s -inputjad %s -outputjad %s" % \
                            (jad_tool, jar_file.name, key_alias, key_store, store_pass, key_pass, jad_file.name, jad_file.name)

            step_two = "java -jar %s -addcert -alias %s -keystore %s -storepass %s -inputjad %s -outputjad %s" % \
                            (jad_tool, key_alias, key_store, store_pass, jad_file.name, jad_file.name)

            for step in (step_one, step_two):
                p = Popen(shlex.split(step), stdout=PIPE, stderr=PIPE, shell=False)
                err = p.stderr.read().strip()
                if err != '': raise Exception(err)

            with open(jad_file.name) as f:
                txt = f.read()
                jad = JadDict.from_jad(txt)
    jad.update({
        "MIDlet-Permissions" : "javax.microedition.io.Connector.file.read,javax.microedition.io.Connector.ssl,javax.microedition.io.Connector.file.write,javax.microedition.io.Connector.comm,javax.microedition.io.Connector.http,javax.microedition.io.Connector.https"
    })
    jad.line_ending = line_ending

    return jad

