#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2015-2016 University of Dundee & Open Microscopy Environment.
# All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import json
import pytest

from omero_cli_render import RenderControl
from omero.cli import NonZeroReturnCode
from cli import CLITest
from omero.gateway import BlitzGateway


# TODO: rdefid, tbid
SUPPORTED = [
    "idonly", "imageid", "plateid", "screenid", "datasetid", "projectid"]


class TestRender(CLITest):

    def setup_method(self, method):
        super(TestRender, self).setup_method(method)
        self.cli.register("render", RenderControl, "TEST")
        self.args += ["render"]
        self.idonly = "-1"
        self.imageid = "Image:-1"
        self.plateid = "Plate:-1"
        self.screenid = "Screen:-1"
        self.datasetid = "Dataset:-1"
        self.projectid = "Project:-1"

    def create_image(self, sizec=4, target_name=None):
        self.gw = BlitzGateway(client_obj=self.client)
        if target_name == "plateid" or target_name == "screenid":
            self.plates = []
            for plate in self.import_plates(client=self.client, fields=2,
                                            sizeC=sizec, screens=1):
                self.plates.append(self.gw.getObject("Plate", plate.id.val))
            # Now pick the first Image
            self.imgobj = list(
                self.plates[0].listChildren())[0].getImage(index=0)
            self.idonly = "%s" % self.imgobj.id
            self.imageid = "Image:%s" % self.imgobj.id
            self.plateid = "Plate:%s" % self.plates[0].id
            self.screenid = "Screen:%s" % self.plates[0].getParent().id
            # And another one as the source for copies
            self.source = list(
                self.plates[0].listChildren())[0].getImage(index=1)
            self.source = "Image:%s" % self.source.id

            # And for all the images, pre-load a thumbnail
            for p in self.plates:
                for w in p.listChildren():
                    for i in range(w.countWellSample()):
                        img = w.getImage(index=i)
                        img.getThumbnail(
                            size=(96,), direct=False)
        else:
            images = self.import_fake_file(images_count=2, sizeC=sizec,
                                           client=self.client)
            self.idonly = "%s" % images[0].id.val
            self.imageid = "Image:%s" % images[0].id.val
            self.source = "Image:%s" % images[1].id.val
            for image in images:
                img = self.gw.getObject("Image", image.id.val)
                img.getThumbnail(size=(96,), direct=False)

        if target_name == "datasetid" or target_name == "projectid":
            # Create Project/Dataset hierarchy
            project = self.make_project(client=self.client)
            self.project = self.gw.getObject("Project", project.id.val)
            dataset = self.make_dataset(client=self.client)
            self.dataset = self.gw.getObject("Dataset", dataset.id.val)
            self.projectid = "Project:%s" % self.project.id
            self.datasetid = "Dataset:%s" % self.dataset.id
            self.link(obj1=project, obj2=dataset)
            for i in images:
                self.link(obj1=dataset, obj2=i)

    def get_target_imageids(self, target):
        if target in (self.idonly, self.imageid):
            return [self.idonly]
        if target == self.plateid:
            imgs = []
            for w in self.plates[0].listChildren():
                imgs.extend([w.getImage(0).id, w.getImage(1).id])
            return imgs
        if target == self.screenid:
            imgs = []
            for s in self.plates:
                for w in self.plates[0].listChildren():
                    imgs.extend([w.getImage(0).id, w.getImage(1).id])
            return imgs
        if target == self.datasetid:
            imgs = []
            for img in self.dataset.listChildren():
                imgs.append(img.id)
            return imgs
        if target == self.projectid:
            imgs = []
            for d in self.project.listChildren():
                for img in d.listChildren():
                    imgs.append(img.id)
            return imgs
        raise Exception('Unknown target: %s' % target)

    def get_render_def(self, sizec=4, greyscale=None, version=2):
        channels = {}
        start = 'start' if version > 1 else 'min'
        end = 'end' if version > 1 else 'max'
        channels[1] = {
            'label': self.uuid(),
            'color': '123456',
            start: 11,
            end: 22,
        }
        channels[2] = {
            'label': self.uuid(),
            'color': '789ABC',
            start: 33,
            end: 44,
        }
        channels[3] = {
            'label': self.uuid(),
            'color': 'DEF012',
            start: 55,
            end: 66,
        }
        channels[4] = {
            'label': self.uuid(),
            'color': '345678',
            start: 77,
            end: 88,
        }

        for k in xrange(sizec, 4):
            del channels[k + 1]
        d = {'channels': channels}

        if greyscale is not None:
            d['greyscale'] = greyscale
        d['version'] = version
        return d

    def assert_target_rdef(self, target, rdef):
        """Check the rendering setting of all images containing in a target"""
        iids = self.get_target_imageids(target)
        gw = BlitzGateway(client_obj=self.client)
        for iid in iids:
            # Get the updated object
            img = gw.getObject('Image', iid)
            # Note: calling _prepareRE below does NOT suffice!
            img._prepareRenderingEngine()  # Call *before* getChannels
            # Passing noRE to getChannels below also prevents leaking
            # the RenderingEngine but then Nones are returned later.
            channels = img.getChannels()
            assert len(channels) == len(rdef['channels'])
            for c in xrange(len(channels)):
                self.assert_channel_rdef(
                    channels[c], rdef['channels'][c + 1],
                    version=rdef['version'])

            if rdef.get('greyscale', None) is None:
                if len(channels) == 1:
                    self.assert_image_rmodel(img, True)
                else:
                    self.assert_image_rmodel(img, False)
            else:
                self.assert_image_rmodel(img, rdef.get('greyscale'))

    def assert_channel_rdef(self, channel, rdef, version=2):
        assert channel.getLabel() == rdef['label']
        assert channel.getColor().getHtml() == rdef['color']
        start = rdef['start'] if version > 1 else rdef['min']
        end = rdef['end'] if version > 1 else rdef['max']
        assert channel.getWindowStart() == start
        assert channel.getWindowEnd() == end

    def assert_image_rmodel(self, img, greyscale):
        assert img.isGreyscaleRenderingModel() == greyscale

    # rendering tests
    # ========================================================================

    @pytest.mark.permissions
    def test_cross_group(self, capsys):
        self.create_image(sizec=1)
        login = self.root_login_args()
        # Run test as self and as root
        self.cli.invoke(self.args + ["test", self.imageid], strict=True)
        self.cli.invoke(login + ["render", "test", self.imageid], strict=True)
        out, err = capsys.readouterr()
        lines = out.split("\n")
        assert "ok" in lines[0]
        assert "ok" in lines[1]

    @pytest.mark.parametrize('target_name', sorted(SUPPORTED))
    def test_non_existing_image(self, target_name, tmpdir):
        self.args += ["info", getattr(self, target_name)]
        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke(self.args, strict=True)

    @pytest.mark.parametrize('target_name', sorted(SUPPORTED))
    def test_info(self, target_name, tmpdir):
        self.create_image(target_name=target_name)
        target = getattr(self, target_name)
        self.args += ["info", target]
        self.cli.invoke(self.args, strict=True)

    @pytest.mark.parametrize('style', ['json', 'yaml'])
    def test_info_style(self, style):
        self.create_image()
        self.args += ["info", self.imageid, "--style", style]
        self.cli.invoke(self.args, strict=True)

    @pytest.mark.parametrize('target_name', sorted(SUPPORTED))
    def test_copy(self, target_name, tmpdir):
        self.create_image(target_name=target_name)
        target = getattr(self, target_name)
        rd = self.get_render_def()
        rdfile = tmpdir.join('render-copy.json')
        self.args += ["set", self.source, str(rdfile)]
        self.args += ["copy", self.source, target]
        self.cli.invoke(self.args, strict=True)
        self.assert_target_rdef(target, rd)

    @pytest.mark.parametrize('sizec', [1, 2, 4])
    @pytest.mark.parametrize('greyscale', [None, True, False])
    @pytest.mark.parametrize('version', [1, 2])
    def test_set(self, sizec, greyscale, version, tmpdir):
        self.create_image(sizec=sizec)
        rd = self.get_render_def(sizec=sizec, greyscale=greyscale,
                                 version=version)
        rdfile = tmpdir.join('render_set.json')
        # Should work with json and yaml, but yaml is an optional dependency
        rdfile.write(json.dumps(rd))
        self.args += ["set", self.idonly, str(rdfile)]
        self.cli.invoke(self.args, strict=True)
        self.assert_target_rdef(self.idonly, rd)

    @pytest.mark.parametrize('target_name', sorted(SUPPORTED))
    @pytest.mark.parametrize('sizec', [1, 2])
    def test_set_target(self, target_name, sizec, tmpdir):
        self.create_image(sizec=sizec, target_name=target_name)
        rd = self.get_render_def(sizec=sizec)
        rdfile = tmpdir.join('render-test-editsinglec.json')
        # Should work with json and yaml, but yaml is an optional dependency
        rdfile.write(json.dumps(rd))
        target = getattr(self, target_name)
        self.args += ["set", target, str(rdfile)]
        self.cli.invoke(self.args, strict=True)
        self.assert_target_rdef(target, rd)
