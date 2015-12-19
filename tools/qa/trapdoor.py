# -*- coding: utf-8 -*-
# HORTON: Helpful Open-source Research TOol for N-fermion systems.
# Copyright (C) 2011-2015 The HORTON Development Team
#
# This file is part of HORTON.
#
# HORTON is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# HORTON is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>
#
# --
"""Shared trapdoor code.

This model provides the ``TrapdoorProgram`` base class for all trapdoor programs.
"""


import argparse
import cPickle
import json
import os
import shutil
import sys
import time


__all__ = ['TrapdoorProgram']


class TrapdoorProgram(object):
    """Base class for all trapdoor programs.

    This class implements all the shared functionality between different specializations
    of the traps door programs, such as the command-line interface, basic configuration
    and some screen output.

    Trapdoor programs must be implemented as follows:

    * Extend the ``__init__`` method, at least providing a sensible name.
    * Optional extend the ``prepare`` method, e.g. to copy config files.
    * Override the ``get_stats`` method, where the real work is done: calling a QA program
      and collecting its output into a standard format.
    * Call ``DerivedTrapdoorProgram().main()``
    """

    def __init__(self, name):
        """Initialize the trapdoor program.

        Parameters
        ----------
        name : str
               The name of the trapdoor program, e.g. ``'cppcheck'``.
        """
        # Set attributes
        self.name = name
        # Get the QAWORKDIR. Create if it does not exist yet.
        self.qaworkdir = os.getenv('QAWORKDIR', 'qaworkdir')
        if not os.path.isdir(self.qaworkdir):
            os.makedirs(self.qaworkdir)
        self.trapdoor_config_file = os.path.join(self.qaworkdir, 'trapdoor.cfg')

    def main(self):
        """Execute the main routine of the trapdoor program.

        This includes parsing command-line arguments and running one of the three modes:
        ``feature``, ``master`` or ``report``.
        """
        args = self.parse_args()
        print r'~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+      ~~~~~~~~~~~~~~~~~'
        print r'  TRAPDOOR %15s:%-7s                      \          _\( )/_' % (
            self.name, args.mode)
        print r'                                                         \          /(o)\ '
        print r'                                                          +~~~~~~~~~~~~~~~~~~~~'
        if args.mode == 'feature':
            self.prepare()
            self.run_tests(args.mode)
        elif args.mode == 'master':
            self.run_tests(args.mode)
        elif args.mode == 'report':
            self.report(args.noisy)
        print

    def parse_args(self):
        """Parse command-line arguments.

        Returns
        -------
        args : argsparse.Namespace
               The parsed command-line arguments.
        """
        parser = argparse.ArgumentParser(prog=os.path.basename(sys.argv[0]))
        parser.add_argument('mode', choices=['feature', 'master', 'report'])
        parser.add_argument('-n', '--noisy', default=False, action='store_true',
                            help='Also print output for problems that did not '
                                 'deteriorate.')
        return parser.parse_args()

    def prepare(self):
        """Prepare for the tests, only once, needed for both feature and master branch.

        This usually comes down to copying some config files to the QAWORKDIR. This method
        is only called when in the feature branch.
        """
        shutil.copy('tools/qa/trapdoor.cfg', self.trapdoor_config_file)

    def run_tests(self, mode):
        """Run the tests on a single branch HEAD.

        Parameters
        ----------
        mode: string
              A name for the current branch on which the tests are run, typically
              ``'feature'`` or ``'master'``.

        The results are written to disk in a file ``trapdoor_results_*.pp``. These files
        are later used by the report method to analyze the results.
        """
        start_time = time.time()
        with open(self.trapdoor_config_file, 'r') as f:
            config = json.load(f)
        counter, messages = self.get_stats(config)
        print 'NUMBER OF MESSAGES :', len(messages)
        print 'SUM OF COUNTERS    :', sum(counter.itervalues())
        fn_pp = 'trapdoor_results_%s_%s.pp' % (self.name, mode)
        with open(os.path.join(self.qaworkdir, fn_pp), 'w') as f:
            cPickle.dump((counter, messages), f)
        print 'WALL TIME %.1f' % (time.time() - start_time)

    def get_stats(self, config):
        """Run tests using an external program and collect its output

        This method must be implemented in a subclass.

        Parameters
        ----------
        config : dict
                 The dictionary loaded from ``trapdoor.cfg``.

        Returns
        -------
        counter : collections.Counter
                  Counts of the number of messages of a specific type in a certain file.
        messages : Set([]) of strings
                   All errors encountered in the current branch.
        """
        raise NotImplementedError

    def report(self, noisy=False):
        """Load feature and master results from disk and report on screen.

        Parameters
        ----------
        noisy : bool
                If True, more detailed screen output is printed.
        """
        fn_pp_feature = 'trapdoor_results_%s_feature.pp' % self.name
        with open(os.path.join(self.qaworkdir, fn_pp_feature)) as f:
            results_feature = cPickle.load(f)
        fn_pp_master = 'trapdoor_results_%s_master.pp' % self.name
        with open(os.path.join(self.qaworkdir, fn_pp_master)) as f:
            results_master = cPickle.load(f)
        if noisy:
            self.print_details(results_feature, results_master)
        self.check_regression(results_feature, results_master)

    def print_details(self, (counter_feature, messages_feature),
                      (counter_master, messages_master)):
        """Print optional detailed report of the test results.

        Parameters
        ----------
        counter_feature : collections.Counter
                          Counts for different error types in the feature branch.
        messages_feature : Set([]) of strings
                           All errors encountered in the feature branch.
        counter_master : collections.Counter
                         Counts for different error types in the master branch.
        messages_master : Set([]) of strings
                          All errors encountered in the master branch.
        """
        resolved_messages = sorted(messages_master - messages_feature)
        if len(resolved_messages) > 0:
            print 'RESOLVED MESSAGES'
            for msg in resolved_messages:
                print msg

        unchanged_messages = sorted(messages_master & messages_feature)
        if len(unchanged_messages) > 0:
            print 'UNCHANGED MESSAGES'
            for msg in unchanged_messages:
                print msg

        resolved_counter = counter_master - counter_feature
        if len(resolved_counter) > 0:
            print 'SOME COUNTERS DECREASED'
            for key, counter in resolved_counter.iteritems():
                print '%s  |  %+6i' % (key, -counter)

    def check_regression(self, (counter_feature, messages_feature),
                         (counter_master, messages_master)):
        """Check if the counters got worse.

        The new errors are printed and if a regression is observed, the program quits with
        an exit status of 1.

        Parameters
        ----------
        counter_feature : collections.Counter
                          Counts for different error types in the feature branch.
        messages_feature : Set([]) of strings
                           All errors encountered in the feature branch.
        counter_master : collections.Counter
                         Counts for different error types in the master branch.
        messages_master : Set([]) of strings
                          All errors encountered in the master branch.
        """
        new_messages = sorted(messages_feature - messages_master)
        if len(new_messages) > 0:
            print 'NEW MESSAGES'
            for msg in new_messages:
                print msg

        new_counter = counter_feature - counter_master
        if len(new_counter) > 0:
            print 'SOME COUNTERS INCREASED'
            for key, counter in new_counter.iteritems():
                print '%s  |  %+6i' % (key, counter)
            sys.exit(1)
        else:
            print 'GOOD ENOUGH'
