using UnityEditor;
using UnityEngine;

public static class LocalVersusInputSetup
{
    private static readonly string[] AxisBases =
    {
        "L_XAxis", "L_YAxis", "DPad_XAxis", "DPad_YAxis",
        "R_XAxis", "R_YAxis", "TriggersL", "TriggersR"
    };

    public static void EnsurePlayerTwoAxes()
    {
        Object inputManager = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/InputManager.asset")[0];
        var serialized = new SerializedObject(inputManager);
        SerializedProperty axes = serialized.FindProperty("m_Axes");

        foreach (string axisBase in AxisBases)
        {
            string sourceName = axisBase + "_1";
            string targetName = axisBase + "_2";
            if (FindAxis(axes, targetName) >= 0)
                continue;

            int source = FindAxis(axes, sourceName);
            if (source < 0)
                throw new System.InvalidOperationException("Missing source legacy input axis: " + sourceName);

            int target = axes.arraySize;
            axes.InsertArrayElementAtIndex(target);
            CopyAxis(axes.GetArrayElementAtIndex(source), axes.GetArrayElementAtIndex(target));
            axes.GetArrayElementAtIndex(target).FindPropertyRelative("m_Name").stringValue = targetName;
            // Unity legacy joystick numbering is 1-based. Player Two uses joystick 2.
            axes.GetArrayElementAtIndex(target).FindPropertyRelative("joyNum").intValue = 2;
        }

        serialized.ApplyModifiedPropertiesWithoutUndo();
        AssetDatabase.SaveAssets();
        Debug.Log("Local versus legacy Player Two axes are configured.");
    }

    private static int FindAxis(SerializedProperty axes, string name)
    {
        for (int i = 0; i < axes.arraySize; i++)
            if (axes.GetArrayElementAtIndex(i).FindPropertyRelative("m_Name").stringValue == name)
                return i;
        return -1;
    }

    private static void CopyAxis(SerializedProperty source, SerializedProperty target)
    {
        var iterator = source.Copy();
        var end = iterator.GetEndProperty();
        bool enterChildren = true;
        while (iterator.Next(enterChildren) && !SerializedProperty.EqualContents(iterator, end))
        {
            enterChildren = false;
            SerializedProperty destination = target.FindPropertyRelative(iterator.name);
            if (destination == null)
                continue;
            switch (iterator.propertyType)
            {
                case SerializedPropertyType.String: destination.stringValue = iterator.stringValue; break;
                case SerializedPropertyType.Integer: destination.intValue = iterator.intValue; break;
                case SerializedPropertyType.Boolean: destination.boolValue = iterator.boolValue; break;
                case SerializedPropertyType.Float: destination.floatValue = iterator.floatValue; break;
            }
        }
    }
}
