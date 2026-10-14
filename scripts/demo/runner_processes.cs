using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

namespace Gateway.Demo
{
    // The job handle stays exclusively in the runner. Windows closes it even
    // when the console is closed or the runner is terminated unexpectedly.
    public sealed class DemoProcessGroup : IDisposable
    {
        private SafeJobHandle job;
        private readonly List<Task> outputReaders = new List<Task>();
        private readonly Native.ConsoleHandler consoleHandler;
        private volatile bool stopRequested;
        private bool disposed;
        private static readonly object OutputLock = new object();

        public bool StopRequested { get { return stopRequested; } }

        public DemoProcessGroup()
        {
            job = Native.CreateJobObject(IntPtr.Zero, null);
            if (job.IsInvalid) throw new Win32Exception();
            try
            {
                Native.ExtendedLimits limits = new Native.ExtendedLimits();
                limits.BasicLimitInformation.LimitFlags = 0x2000; // KILL_ON_JOB_CLOSE
                if (!Native.SetInformationJobObject(job, 9, ref limits,
                    (uint)Marshal.SizeOf(typeof(Native.ExtendedLimits))))
                    throw new Win32Exception();
                consoleHandler = HandleConsoleEvent;
                if (!Native.SetConsoleCtrlHandler(consoleHandler, true))
                    throw new Win32Exception();
            }
            catch { job.Dispose(); throw; }
        }

        private bool HandleConsoleEvent(uint eventType)
        {
            if (eventType == 0 || eventType == 1) // Ctrl+C / Ctrl+Break
            {
                stopRequested = true;
                return true; // Let the polling runner unwind normally.
            }
            // For console close, Windows terminates the host and closes the
            // non-inherited job handle. No PowerShell cleanup is required.
            return false;
        }

        public Process Start(string executable, string arguments,
            string workingDirectory, string logPath)
        {
            if (disposed) throw new ObjectDisposedException("DemoProcessGroup");
            if (stopRequested) throw new OperationCanceledException();
            IntPtr readPipe = IntPtr.Zero, writePipe = IntPtr.Zero;
            IntPtr attributes = IntPtr.Zero, jobValue = IntPtr.Zero;
            bool attributesInitialized = false;
            Native.ProcessInformation info = new Native.ProcessInformation();
            StreamReader reader = null;
            StreamWriter log = null;
            try
            {
                Native.SecurityAttributes security = new Native.SecurityAttributes();
                security.Length = Marshal.SizeOf(typeof(Native.SecurityAttributes));
                security.InheritHandle = true;
                if (!Native.CreatePipe(out readPipe, out writePipe, ref security, 0))
                    throw new Win32Exception();
                if (!Native.SetHandleInformation(readPipe, 1, 0))
                    throw new Win32Exception();

                IntPtr attributeSize = IntPtr.Zero;
                Native.InitializeProcThreadAttributeList(IntPtr.Zero, 1, 0, ref attributeSize);
                if (attributeSize == IntPtr.Zero) throw new Win32Exception();
                attributes = Marshal.AllocHGlobal(attributeSize);
                if (!Native.InitializeProcThreadAttributeList(attributes, 1, 0, ref attributeSize))
                    throw new Win32Exception();
                attributesInitialized = true;
                jobValue = Marshal.AllocHGlobal(IntPtr.Size);
                Marshal.WriteIntPtr(jobValue, job.DangerousGetHandle());
                // Windows 10+: membership is assigned atomically at creation.
                // Even termination inside CreateProcess cannot leave an unowned child.
                if (!Native.UpdateProcThreadAttribute(attributes, 0, new UIntPtr(0x2000d),
                    jobValue, new UIntPtr((uint)IntPtr.Size), IntPtr.Zero, IntPtr.Zero))
                    throw new Win32Exception();

                Native.StartupInfoEx startup = new Native.StartupInfoEx();
                startup.Info.Size = Marshal.SizeOf(typeof(Native.StartupInfoEx));
                startup.Info.Flags = 0x100; // STARTF_USESTDHANDLES
                startup.Info.StandardInput = Native.GetStdHandle(-10);
                startup.Info.StandardOutput = writePipe;
                startup.Info.StandardError = writePipe;
                startup.Attributes = attributes;
                StringBuilder command = new StringBuilder("\"" + executable + "\" " + arguments);
                if (!Native.CreateProcess(executable, command, IntPtr.Zero,
                    IntPtr.Zero, true, 0x80004, IntPtr.Zero, workingDirectory,
                    ref startup, out info)) // EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED
                    throw new Win32Exception();

                Native.CloseHandle(writePipe);
                writePipe = IntPtr.Zero;
                reader = new StreamReader(new FileStream(
                    new SafeFileHandle(readPipe, true), FileAccess.Read), Encoding.UTF8);
                readPipe = IntPtr.Zero;
                log = new StreamWriter(logPath, false, new UTF8Encoding(false));
                log.AutoFlush = true;
                StreamReader ownedReader = reader;
                StreamWriter ownedLog = log;
                outputReaders.Add(Task.Factory.StartNew(delegate
                {
                    using (ownedReader)
                    using (ownedLog)
                    {
                        string line;
                        while ((line = ownedReader.ReadLine()) != null)
                        {
                            ownedLog.WriteLine(line);
                            lock (OutputLock) { Console.WriteLine(line); }
                        }
                    }
                }, TaskCreationOptions.LongRunning));
                reader = null;
                log = null;
                Process process = Process.GetProcessById((int)info.ProcessId);
                if (Native.ResumeThread(info.Thread) == UInt32.MaxValue)
                {
                    process.Dispose();
                    throw new Win32Exception();
                }
                return process;
            }
            catch
            {
                // Before ResumeThread a failed launch has no descendants.
                if (info.Process != IntPtr.Zero)
                {
                    Native.TerminateProcess(info.Process, 1);
                    Native.WaitForSingleObject(info.Process, 5000);
                }
                // Already assigned children also remain protected by the job.
                throw;
            }
            finally
            {
                if (attributesInitialized) Native.DeleteProcThreadAttributeList(attributes);
                if (attributes != IntPtr.Zero) Marshal.FreeHGlobal(attributes);
                if (jobValue != IntPtr.Zero) Marshal.FreeHGlobal(jobValue);
                if (readPipe != IntPtr.Zero) Native.CloseHandle(readPipe);
                if (writePipe != IntPtr.Zero) Native.CloseHandle(writePipe);
                if (info.Thread != IntPtr.Zero) Native.CloseHandle(info.Thread);
                if (info.Process != IntPtr.Zero) Native.CloseHandle(info.Process);
                if (reader != null) reader.Dispose();
                if (log != null) log.Dispose();
            }
        }

        public bool WaitForExit(int timeoutMilliseconds)
        {
            Stopwatch timeout = Stopwatch.StartNew();
            do
            {
                Native.Accounting information;
                if (!Native.QueryInformationJobObject(job, 1, out information,
                    (uint)Marshal.SizeOf(typeof(Native.Accounting)), IntPtr.Zero))
                    throw new Win32Exception();
                if (information.ActiveProcesses == 0) return true;
                Thread.Sleep(50);
            } while (timeout.ElapsedMilliseconds < timeoutMilliseconds);
            return false;
        }

        public void Dispose()
        {
            if (disposed) return;
            disposed = true;
            try
            {
                // Verify normal cleanup before closing the last job handle.
                if (!Native.TerminateJobObject(job, 0)) throw new Win32Exception();
                if (!WaitForExit(5000))
                    throw new TimeoutException("The owned process tree did not stop.");
            }
            finally
            {
                // Closing the handle remains the fallback on every error path.
                job.Dispose();
                Native.SetConsoleCtrlHandler(consoleHandler, false);
                if (outputReaders.Count > 0 && !Task.WaitAll(outputReaders.ToArray(), 3000))
                    throw new TimeoutException("The server logs did not finish draining.");
                GC.KeepAlive(consoleHandler);
            }
        }

        private sealed class SafeJobHandle : SafeHandleZeroOrMinusOneIsInvalid
        {
            public SafeJobHandle() : base(true) { }
            protected override bool ReleaseHandle() { return Native.CloseHandle(handle); }
        }

        private static class Native
        {
            [UnmanagedFunctionPointer(CallingConvention.Winapi)]
            public delegate bool ConsoleHandler(uint eventType);
            [StructLayout(LayoutKind.Sequential)]
            public struct SecurityAttributes
            {
                public int Length;
                public IntPtr SecurityDescriptor;
                [MarshalAs(UnmanagedType.Bool)] public bool InheritHandle;
            }
            [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
            public struct StartupInfo
            {
                public int Size;
                public string Reserved, Desktop, Title;
                public uint X, Y, XSize, YSize, XCountChars, YCountChars, FillAttribute, Flags;
                public ushort ShowWindow, ReservedSize;
                public IntPtr ReservedBytes, StandardInput, StandardOutput, StandardError;
            }
            [StructLayout(LayoutKind.Sequential)]
            public struct StartupInfoEx
            {
                public StartupInfo Info;
                public IntPtr Attributes;
            }
            [StructLayout(LayoutKind.Sequential)]
            public struct ProcessInformation
            {
                public IntPtr Process, Thread;
                public uint ProcessId, ThreadId;
            }
            [StructLayout(LayoutKind.Sequential)]
            public struct BasicLimits
            {
                public long ProcessUserTime, JobUserTime;
                public uint LimitFlags;
                public UIntPtr MinimumWorkingSet, MaximumWorkingSet;
                public uint ActiveProcessLimit;
                public UIntPtr Affinity;
                public uint PriorityClass, SchedulingClass;
            }
            [StructLayout(LayoutKind.Sequential)]
            public struct IoCounters
            {
                public ulong ReadOperations, WriteOperations, OtherOperations;
                public ulong ReadBytes, WriteBytes, OtherBytes;
            }
            [StructLayout(LayoutKind.Sequential)]
            public struct ExtendedLimits
            {
                public BasicLimits BasicLimitInformation;
                public IoCounters IoInfo;
                public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemory, PeakJobMemory;
            }
            [StructLayout(LayoutKind.Sequential)]
            public struct Accounting
            {
                public long ProcessUserTime, JobUserTime, PeriodProcessTime, PeriodJobTime;
                public uint PageFaults, TotalProcesses, ActiveProcesses, TerminatedProcesses;
            }

            [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
            public static extern SafeJobHandle CreateJobObject(IntPtr security, string name);
            [DllImport("kernel32.dll", SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool SetInformationJobObject(SafeJobHandle job, int kind,
                ref ExtendedLimits information, uint length);
            [DllImport("kernel32.dll", SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool QueryInformationJobObject(SafeJobHandle job, int kind,
                out Accounting information, uint length, IntPtr returnedLength);
            [DllImport("kernel32.dll", SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool InitializeProcThreadAttributeList(IntPtr list, int count,
                int flags, ref IntPtr size);
            [DllImport("kernel32.dll", SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool UpdateProcThreadAttribute(IntPtr list, uint flags,
                UIntPtr attribute, IntPtr value, UIntPtr size, IntPtr previous, IntPtr returned);
            [DllImport("kernel32.dll")]
            public static extern void DeleteProcThreadAttributeList(IntPtr list);
            [DllImport("kernel32.dll", SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool TerminateJobObject(SafeJobHandle job, uint exitCode);
            [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool CreateProcess(string application, StringBuilder command,
                IntPtr processSecurity, IntPtr threadSecurity,
                [MarshalAs(UnmanagedType.Bool)] bool inheritHandles, uint flags,
                IntPtr environment, string workingDirectory, ref StartupInfoEx startup,
                out ProcessInformation information);
            [DllImport("kernel32.dll", SetLastError = true)]
            public static extern uint ResumeThread(IntPtr thread);
            [DllImport("kernel32.dll", SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool CreatePipe(out IntPtr read, out IntPtr write,
                ref SecurityAttributes security, uint size);
            [DllImport("kernel32.dll", SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool SetHandleInformation(IntPtr handle, uint mask, uint flags);
            [DllImport("kernel32.dll", SetLastError = true)]
            public static extern IntPtr GetStdHandle(int kind);
            [DllImport("kernel32.dll", SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool SetConsoleCtrlHandler(ConsoleHandler handler,
                [MarshalAs(UnmanagedType.Bool)] bool add);
            [DllImport("kernel32.dll", SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool TerminateProcess(IntPtr process, uint exitCode);
            [DllImport("kernel32.dll", SetLastError = true)]
            public static extern uint WaitForSingleObject(IntPtr handle, uint timeout);
            [DllImport("kernel32.dll", SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool CloseHandle(IntPtr handle);
        }
    }
}
